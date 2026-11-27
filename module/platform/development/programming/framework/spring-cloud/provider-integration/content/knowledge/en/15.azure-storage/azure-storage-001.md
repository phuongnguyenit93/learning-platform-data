# Distinguishing Blob Storage, File Share, and Storage Queue in Azure

## 1. Context and Objectives

When integrating a Spring Boot application with Azure's managed storage services, the three names **Azure Blob Storage**, **Azure Files (File Share)**, and **Azure Queue Storage** are easy to confuse because they all belong to the Azure Storage family. However, they address **three different needs**:

- **Blob Storage**: stores and retrieves **data objects** such as images, videos, PDF files, backups, or system-generated exports.
- **Azure Files / File Share**: provides a **shared file system** with directories and files, typically accessed by applications or servers over SMB/NFS.
- **Queue Storage**: stores **work messages** for components to process asynchronously; this is not a place to store file contents.

This lesson belongs to the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, focusing on choosing the right managed service, integrating with Spring Boot/Spring Cloud Azure, configuring access permissions, designing processing flows, and testing. After this lesson, you should be able to explain *why* a given problem calls for Blob, File Share, or Queue, and know how to combine them without mixing up their roles.

## 2. Quick Comparison

| Criterion | Azure Blob Storage | Azure Files (File Share) | Azure Queue Storage |
|---|---|---|---|
| Primary data unit | Blob (object) inside a container | Files, directories inside a file share | Message inside a queue |
| Primary use case | Storing unstructured content, uploading/downloading via API | Shared directories, applications needing filesystem-style operations | Dispatching tasks, decoupling producer and consumer |
| Typical access method | HTTPS/REST, Azure SDK, URL/SAS | SMB/NFS for mounting; also REST/SDK | HTTPS/REST, Azure SDK, producer/worker |
| Addressing scheme | Storage account → container → blob name | Storage account → share → directory → file | Storage account → queue → message |
| Common operations | Upload, download, list, delete, metadata, versioning | Create directory, open/read/write file, share via path | Enqueue, receive, process, delete message |
| Semantics to note | Object storage; `/` in a name does not mean a real directory in standard configurations | Has directory hierarchy, operations, and file locking according to the protocol used | Duplicate delivery can occur; ordering is not guaranteed |
| Examples | Product images, PDF records, export files, archived logs | Report directories for multiple VMs/containers, file server replacement | Requests for thumbnail generation, sending emails, document processing |
| **Should not be used as** | A shared drive requiring full SMB semantics | A store of billions of objects accessed only via URL without needing a filesystem | A store for PDFs/videos or a queue needing transactions/complex topic-based fan-out |

**Rule of thumb:** need to *store content* → think **Blob**; need to *mount a shared directory* → think **Azure Files**; need to *send a job for later processing* → think **Queue**. A business flow can use all three, though it does not necessarily have to use all three services.

## 3. Blob Storage: Storing Objects and Serving Content

Blob Storage organizes data by **storage account → container → blob**. Each blob has a name (key), content, and metadata. Applications typically use the Azure SDK or REST to upload/download; browser clients can use appropriately authorized URLs. Blob names like `customers/42/avatar.png` help group objects by prefix; in a standard Blob account, slashes in the name do not automatically turn Blob into a file system with full POSIX semantics. Azure Data Lake Storage Gen2 with hierarchical namespace is a separate case with dedicated directory capabilities.

Blob types to know:

- **Block blob**: the common choice for documents, images, media, and uploaded data.
- **Append blob**: optimized for append-only writes, such as certain log streams.
- **Page blob**: supports page-based read/write; used for scenarios like virtual disks.

Blob Storage fits **upload once, retrieve many times** flows, key-based upload/download, serving large content, and lifecycle-based archiving. Protection mechanisms such as blob versioning, soft delete, lifecycle rules, and supported access tiers (depending on account/data type) can be used. Choose an access tier based on access frequency, retention duration, and data retrieval cost, rather than defaulting all data to `Hot`.

**Example:** an e-commerce application stores product images in the `product-images` container. The database only stores the blob name or reference URL, business metadata, and relationship to the product; the actual image file resides in Blob Storage. When returning a private file to a user, the backend authenticates access rights before downloading the content or issuing a SAS with minimal permissions and lifetime.

**Common pitfall:** Blob Storage can list blobs by prefix, but this does not make it an equivalent alternative to Azure Files for applications that need to open many files through an SMB directory, perform filesystem-style file locking, or use a shared mount path.

## 4. Azure Files / File Share: Shared Directories and Files

Azure Files provides **managed file shares** inside a storage account. The structure is **share → directory → file**. Servers or applications can mount a file share using a supported protocol, typically **SMB** or **NFS**, and interact through filesystem paths just like a traditional shared drive. Azure Files also provides REST APIs and the Azure Storage Files SDK for programmatic access.

Typical scenarios:

- Migrating a legacy application that reads/writes `\\fileserver\reports` to the cloud without rewriting the entire file-access layer.
- Allowing multiple VMs or containers to read a shared document directory when the deployment architecture and mount protocol permit.
- Providing shared report, configuration, or data directories with a clear directory hierarchy.

For example, once infrastructure mounts the share at `/mnt/reports`, Java code can use familiar filesystem APIs:

~~~java
Path report = Path.of("/mnt/reports/2026/summary.csv");
Files.createDirectories(report.getParent());
Files.writeString(report, "month,total\n11,1250\n");
~~~

This code **assumes the share is already mounted and the process account has write permission**; Spring Boot itself does not perform the mount. Without mounting, the application can use the Azure Files SDK. Availability of SMB/NFS, authentication, authorization, protocol features, and share types depend on the specific Azure Files configuration; verify these before choosing it for a runtime environment.

Do not choose File Share just because the data "is a file". If the actual requirement is uploading images, storing PDFs, and serving download URLs for web/mobile, Blob usually has a better-suited access model. Azure Files provides value when **directory paths and filesystem interaction are genuine architectural requirements**.

## 5. Queue Storage: Decoupling Asynchronous Processing

Azure Queue Storage holds **messages**, not files. Producers write messages to the queue; one or more workers read and process them. Each message should be small and carry just enough information for the worker to locate the business data, for example `{"blobName":"incoming/7f2a.pdf","jobType":"INDEX"}`. For large messages or binary data, store the payload in Blob and **put the blob name/ID in the queue**. The content size limit for a single Azure Queue Storage message is **64 KiB**.

A typical processing cycle:

1. The API receives a request and uploads the file to Blob Storage.
2. The API sends a message containing `blobName` to Storage Queue.
3. A worker receives the message; the message is temporarily hidden during the **visibility timeout**.
4. The worker fetches the data from Blob and processes it.
5. **Only after processing succeeds**, the worker deletes the message using its message ID and pop receipt. If the worker fails or does not delete it, the message can reappear to be processed again.

~~~mermaid
flowchart LR
    C[Client] -->|Upload PDF| A[Spring Boot API]
    A -->|Store PDF content| B[(Blob Storage)]
    A -->|Send blobName + jobId| Q[(Storage Queue)]
    Q -->|Receive job| W[Spring Boot Worker]
    W -->|Read PDF| B
    W -->|Write result/idempotency| D[(Database)]
    W -->|Delete message after success| Q
~~~

Queue Storage is typically used as a **work queue with competing consumers**, meaning multiple workers can concurrently pick up different jobs. It does not guarantee strict ordering, does not provide exactly-once processing, and is not a publish/subscribe mechanism that broadcasts a single message to every subscriber. Consumers must be **idempotent** (re-processing the same job without producing incorrect results), track retry counts (`dequeue count`), and have a strategy to move persistently failing jobs to an application-managed **poison queue**. Queue Storage does not provide a built-in dead-letter queue like Azure Service Bus.

If you need session-controlled FIFO, transactions, a built-in dead-letter queue, or topic-based publish/subscribe, evaluate **Azure Service Bus**. If you need event routing to multiple destinations, evaluate **Event Grid**. If you need high-throughput event streaming, evaluate **Event Hubs**. These services address different problem classes from Storage Queue.

## 6. Hands-On Integration with Spring Boot and Spring Cloud Azure

Suppose an application needs to **accept PDF documents and enqueue them for indexing**. Choose Blob to store the documents and Queue to coordinate processing. File Share is not needed because there is no requirement to mount a shared directory.

### 6.1. Declaring Dependencies and Configuration

With Maven, choose the **Spring Cloud Azure BOM compatible with your Spring Boot version** and add the corresponding starters:

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
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

In `application.yml`, keep the storage account name in an environment variable:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
        queue:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
~~~

The example above assumes **the `documents` container and the `document-jobs` queue have already been created**. Two separate storage accounts can be used if permission, cost, or operational requirements differ. Spring Cloud Azure's credential mechanism should be configured appropriately for each environment: developer login when running locally and **managed identity** in Azure are common choices. Never hardcode account keys, connection strings, or client secrets into Git.

### 6.2. API to Save a Blob Then Send a Queue Message

This code uses clients that Spring Cloud Azure can auto-configure from the starters:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueClient;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final BlobContainerClient documents;
    private final QueueClient jobs;

    public DocumentController(BlobServiceClient blobService,
                              QueueServiceClient queueService) {
        this.documents = blobService.getBlobContainerClient("documents");
        this.jobs = queueService.getQueueClient("document-jobs");
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> upload(@RequestParam("file") MultipartFile file)
            throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File must not be empty");
        }

        String blobName = UUID.randomUUID() + ".pdf";
        try (var stream = file.getInputStream()) {
            documents.getBlobClient(blobName)
                     .upload(stream, file.getSize(), false);
        }

        jobs.sendMessage(blobName);
        return Map.of("blobName", blobName, "state", "QUEUED");
    }
}
~~~

This implementation demonstrates the responsibilities of the two services; for production readiness, you need **content/format validation, size limits, user authentication, document read authorization, logging, and error handling**. The `.pdf` extension in the example does not verify that the file is genuinely a PDF.

An important point: if the Blob upload succeeds but `sendMessage` fails, an unqueued blob will be left behind. **Blob and Queue do not have cross-service transactions**. The system needs a recovery mechanism: recording the job in a database in a pending state, controlled retries, an outbox, or a reconciliation process for unprocessed blobs. Avoid claiming the API will "always guarantee both operations succeed".

### 6.3. Worker Receiving, Processing, and Deleting Messages

The condensed example below uses the SDK directly; `@EnableScheduling` must be enabled in the Spring Boot configuration:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DocumentWorker {
    private static final Logger log =
            LoggerFactory.getLogger(DocumentWorker.class);

    private final BlobContainerClient documents;
    private final QueueClient jobs;

    public DocumentWorker(BlobServiceClient blobService,
                          QueueServiceClient queueService) {
        this.documents = blobService.getBlobContainerClient("documents");
        this.jobs = queueService.getQueueClient("document-jobs");
    }

    @Scheduled(fixedDelayString = "PT5S")
    public void poll() {
        jobs.receiveMessages(4).forEach(message -> {
            try {
                String blobName = message.getBody().toString();
                var blob = documents.getBlobClient(blobName);
                var content = blob.downloadContent();

                // TODO: check whether jobId was already processed, index the document,
                //       and save the result keyed by idempotency key in the database.
                indexDocument(blobName, content.toBytes());

                jobs.deleteMessage(message.getMessageId(),
                                   message.getPopReceipt());
            } catch (Exception ex) {
                log.warn("Failed to process queue message; will retry per policy",
                         ex);
            }
        });
    }

    private void indexDocument(String key, byte[] bytes) {
        // Implement document processing and idempotency here.
    }
}
~~~

**Limitations of the example:** `indexDocument` is a placeholder for business logic, not a complete indexer. `downloadContent().toBytes()` is only suitable for small files; large files should be read via streams or processed in chunks to avoid excessive memory usage. The message invisibility duration must be long enough for a processing pass, or the worker must extend visibility appropriately. When failures repeat many times, the application needs to check `dequeue count` and move the message to a poison queue while recording operational telemetry. Deleting the message must happen **after** the result has been saved successfully.

### 6.4. If the Problem Truly Needs Azure Files

A report-generation service running on multiple instances that must write to the same `/mnt/reports` directory tree can use Azure Files. Two implementation options:

1. **Mount the file share** via SMB/NFS (if infrastructure and protocols support it), then use `java.nio.file.Files` as in section 4.
2. **Use the Azure Files SDK** (`com.azure:azure-storage-file-share`) to access shares/directories/files over REST without mounting.

Choose the appropriate authentication/authorization mechanism for **SMB/NFS** or **REST**; they do not share the same permission model. Do not assume that assigning a data-plane role for Blob automatically grants permissions for File Share.

## 7. Authentication, Authorization, and Data Protection

In an Azure environment, prefer **Microsoft Entra ID and managed identity** when the SDK, service, and access method support them. With Spring Cloud Azure, centralized credential configuration helps keep secrets out of source code. Having management-plane permissions on a storage account **does not automatically mean** the application has all data read/write permissions.

| Service / access method | What to configure |
|---|---|
| Blob via Azure SDK/REST | Appropriate data-plane RBAC, e.g., **Storage Blob Data Contributor** when uploads are needed; scope containers and application identities to least privilege |
| Queue via Azure SDK/REST | Appropriate data-plane RBAC, e.g., **Storage Queue Data Contributor** for producers/workers that need to send, receive, and delete messages; separate permissions if roles allow |
| Azure Files via SMB | Appropriate authentication configuration (such as identity integration), share permissions, and file/directory ACLs per the SMB model |
| Azure Files via REST/SDK | Credential mechanism and roles/permissions compatible with the API/SDK version, OAuth support, and operation types in use |

Alongside least privilege are **HTTPS/TLS**, restricting public access, firewalls/private endpoints where appropriate, data encryption, audit logs, and storage lifecycles. If issuing a **SAS**, grant only the required resource, permissions, and validity period; do not put long-lived SAS tokens in logs or public documentation. Secrets must be protected using tools like **Azure Key Vault** if a deployment scenario mandates using secrets.

## 8. Integration Testing and Common Pitfalls

To verify a Spring Boot + Azure Storage design, test **both success flows and failure flows**:

| Test case | What to verify |
|---|---|
| Upload document | Blob exists with correct content and metadata; API does not inadvertently expose private data publicly |
| Enqueue job | Queue has a message carrying the ID/blob name; worker locates the right Blob |
| Worker succeeds | Business result is saved; message is deleted; reprocessing the same job creates no duplicate records |
| Worker fails mid-way | Message can reappear after visibility timeout; retry does not corrupt data |
| Repeatedly failing message | Retry threshold, poison queue, alerting, and manual remediation path are in place |
| Missing permissions or network block | Application reports diagnosable errors; does not fall back to hardcoded keys |
| Blob saved but queue send fails | Retry/reconciliation exists so jobs are not dropped |
| Using File Share | Two processes access the expected path; mount permissions/ACLs, file locking, and consistency match business needs |

**Azurite** is useful for local testing of Blob/Queue, but it is not a full replica of all Azure Storage features and **does not support Azure Files** as a real file share. Testing Entra ID permissions, private endpoints, SMB/NFS mounts, limits, and operational characteristics requires a test Azure environment. When writing integration tests, use dedicated test data/accounts, clean up resources per the test lifecycle, and intentionally send duplicate messages to verify idempotency.

Common mistakes:

- Stuffing entire PDFs or large payloads into a Queue message instead of storing them in Blob.
- Storing image contents in File Share just because "an image is a file", even though the app only uploads and downloads over HTTP.
- Treating Blob like a filesystem with file locking/mount paths and expecting all operations to behave like SMB.
- Deleting the Queue message **before** business processing finishes, causing failed jobs to be lost.
- Assuming Queue messages arrive at a worker exactly once and always in the exact order sent.
- Testing locally with an account key and forgetting to verify managed identity data-plane permissions when deploying to Azure.

## 9. Scenario Exercises and Self-Check Questions

**Scenario A — Recruitment application:** Users submit PDF resumes, the backend stores the file, and an OCR worker extracts text. **Solution:** Blob holds the resume; Queue holds the `cvId`/`blobName` job; the worker reads Blob, processes idempotently, and deletes the message when done. File Share is unnecessary if there is no mounted directory requirement.

**Scenario B — Legacy accounting application:** Multiple servers run a program that writes files by directory path and shares Excel files between processes. **Solution:** consider Azure Files and verify SMB/NFS, ACLs, file locking, latency, and deployment model. Moving straight to Blob could require rewriting filesystem logic.

**Scenario C — Broadcasting notifications to three independent systems:** Every event must be received by three applications, with independent retry and dead-letter rules. **Solution:** a single Storage Queue does not fan out the same message to all three consumers; consider Azure Service Bus Topics or Event Grid depending on required semantics.

Answer on your own before looking at the hints:

1. Why should a Queue hold `blobName` instead of file contents? — Because the message size limit is small and Queue's role is job coordination, whereas Blob is meant for storing large data.
2. When does Azure Files have a clear advantage over Blob? — When the application needs directories/mount paths, file sharing, and filesystem operations.
3. What happens if a worker finishes business processing but crashes before deleting the message? — The message can be redelivered; idempotency is required to avoid erroneous processing or duplicate results.
4. Why might assigning management permissions on a storage account not enable the SDK to upload Blobs? — Because resource management permissions and data access permissions (data plane) are two separate scopes that must be configured independently.

## 10. Summary

**Blob = content**, **File Share = shared filesystem**, **Queue = work dispatch messages**. In modern Spring Boot applications, the **Blob + Queue** combination is common when uploading and processing asynchronously; **Azure Files** only shines when the business flow genuinely needs directory/file sharing with filesystem semantics. Choose the service based on access patterns, consistency/reprocessing semantics, identity requirements, and operations; then test success cases, failures, access permissions, and recovery scenarios.

### Official References

- [Microsoft Learn — Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Microsoft Learn — What is Azure Files?](https://learn.microsoft.com/azure/storage/files/storage-files-introduction)
- [Microsoft Learn — Introduction to Azure Queue Storage](https://learn.microsoft.com/azure/storage/queues/storage-queues-introduction)
- [Microsoft Learn — Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)

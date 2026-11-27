# Bucket, Object Name, Generation, and Metadata on Google Cloud

## 1. Context: Object Storage on Google Cloud

A Spring Boot application may need to store user documents, images, report exports, log files, or data exchanged between services. On Google Cloud, the common object storage service is **Cloud Storage**. Applications organize data in a **bucket**, identify each object with an **object name**, track data versions via **generation**, and describe content with **metadata**.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions, storage, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson lays the foundation for the Google Cloud Storage track before implementing Spring adapters and integration tests.

After this lesson, you will be able to:

- Distinguish between project, bucket, object name, and object data.
- Explain why `/` in an object name is usually only a prefix convention, not an actual directory by default.
- Distinguish **generation** from **metageneration**, and understand versioning and preconditions.
- Choose system metadata and custom metadata for the right purpose.
- Design bucket/object names, location, storage class, access permissions, and lifecycle policies.
- Call Cloud Storage from Java/Spring Boot using the client library and Application Default Credentials.
- Test uploading, reading, updating metadata, and handling write conflicts safely.

> **Scope:** This lesson focuses on Google Cloud Storage (GCS) and the **google-cloud-storage** Java client library. Examples of buckets, projects, regions, and object names are illustrative data. Spring Cloud GCP/Google Cloud Spring artifacts, APIs, and configurations must be chosen according to releases compatible with the project's Spring Boot and Java versions.

## 2. Resource Model: Project, Bucket, and Object

Cloud Storage stores data as objects. An object consists of **data (bytes)**, an **identifying name**, a **generation**, and **metadata**. Objects are contained in a bucket; a bucket belongs to a Google Cloud project.

~~~mermaid
flowchart TD
    P["Google Cloud project"] --> B["Cloud Storage bucket"]
    B --> O1["Object: reports/2026/report-001.pdf"]
    B --> O2["Object: avatars/user-123.png"]
    B --> O3["Object: exports/daily.csv"]
    O1 --> G1["Generation: data version"]
    O1 --> M1["Metageneration: metadata version"]
~~~

| Component | Example | Role |
| --- | --- | --- |
| Project | **training-platform-dev** | Boundary for management, IAM, billing, and quota |
| Bucket | **training-documents-dev** | Storage container for objects, with location and configuration |
| Object name | **reports/2026/report-001.pdf** | Identifies the object within the bucket |
| Object data | PDF content | Sequence of stored bytes |
| Generation | **1740000000000000** (illustrative) | Identifies a data version of an object |
| Metageneration | **3** (illustrative) | Identifies a metadata version of a generation |

The path **gs://training-documents-dev/reports/2026/report-001.pdf** is the representation of a bucket and object name in GCP tools. It is **not** a local file path and is not a public HTTP URL that anyone can download from.

### 2.1. A Bucket Is an Important Configuration Boundary

A bucket has attributes and policies that affect every object inside it, for example:

- **Location:** region, dual-region, or multi-region.
- **Default storage class:** the default storage class for new objects unless specified otherwise.
- **Access control:** IAM and, if the legacy model is enabled, ACLs.
- **Uniform bucket-level access (UBLA):** unifies permission management via IAM at the bucket/project level.
- **Public access prevention:** prevents accidentally granting public access.
- **Object versioning:** retains old generations when an object is overwritten or deleted under versioning semantics.
- **Lifecycle management:** automatically transitions storage classes or deletes objects/versions based on conditions.
- **Retention policy / Bucket Lock:** controls retention duration and the ability to modify the policy.

A bucket belongs to a specific project; permissions to create a bucket, view a bucket, and access objects are separate IAM permissions. You should not treat a bucket name as a secret or use a bucket name in place of access control checks.

### 2.2. Bucket Names and Locations

Cloud Storage bucket names must follow GCP naming rules and be globally unique within the Cloud Storage namespace. Because the name is used in many URIs/hostnames, choose stable names that clearly identify the environment and avoid personal information or sensitive data. Use gcloud or the API to verify a valid name before provisioning.

Examples:

- **acme-documents-dev**
- **acme-documents-staging**
- **acme-documents-prod**

You should not use a single shared bucket across all environments just to reduce resource count. Separating buckets/projects helps isolate IAM, lifecycle, data, and cost.

Location determines where data is stored and can affect latency, availability, data compliance, and network costs. Choose a location suited to the application and data requirements before creating the bucket; **you should not design workflows assuming you can arbitrarily change a bucket's location after it is in use**. Storage class is a separate decision from location: the same location can hold objects in different storage classes according to supported configurations.

## 3. Bucket Location and Storage Class

### 3.1. Location

Cloud Storage supports typical location types:

| Location type | General meaning | When to consider |
| --- | --- | --- |
| Region | Data is placed in a single region | Applications needing a specific location, low latency near workloads, or data residency requirements |
| Dual-region | Data is stored in a pair of regions per GCP configuration | Need higher availability/resilience across two supported regions |
| Multi-region | Data is placed across a broader geographic area | Distributed access and wide-area availability requirements |

Location is not an attribute of the object name. Do not encode **asia-southeast1** into every key to simulate location; location belongs to the bucket. If the application needs to store data in multiple regions, it can manage multiple buckets and route based on business requirements.

### 3.2. Storage Class

Common storage classes:

- **Standard:** frequently accessed data.
- **Nearline:** infrequently accessed data, usually with a suitable retention period.
- **Coldline:** rarely accessed data.
- **Archive:** very rarely accessed data, oriented toward long-term archiving.

Storage class affects storage pricing, retrieval costs, minimum storage durations, or related fees according to service terms. Do not look only at price per GB when choosing a class; evaluate read frequency, lifecycle, retrieval fees, and recovery needs.

A bucket has a default storage class; each object also has an actual storage class. Lifecycle rules can automatically transition classes based on age or conditions, depending on configuration. Therefore, when analyzing a specific object, read the **object's** storage class rather than inferring it solely from the bucket name.

## 4. Object Name: Identifier, Prefix, and Data Organization

### 4.1. Cloud Storage Has a Flat Namespace by Default

In a bucket using a flat namespace, an object name is an identifying string. The `/` character is part of the object name, commonly used as a **conventional delimiter** to group objects by prefix.

Example of three objects:

~~~text
reports/2026/january.csv
reports/2026/february.csv
reports/2025/annual.csv
~~~

Cloud Console and other tools often display prefixes like **reports/2026/** as folders for easier browsing. However, in the flat namespace model, these "folders" are typically **not independent directory resources**. The actual object is the full name string.

This leads to several consequences:

- **reports/2026/january.csv** is a single object name.
- The prefix **reports/2026/** helps filter the object listing.
- Deleting the object **reports/2026/january.csv** does not mean deleting a physical directory.
- An object named **reports/2026/** can exist as an empty object; the console displaying folder markers does not turn every prefix into a directory.

### 4.2. Hierarchical Namespace Is a Separate Option

Cloud Storage supports **hierarchical namespace (HNS)** for appropriately configured buckets. When HNS is enabled, folders become resources with a more explicit hierarchical structure and can support folder operations such as directory-level renames according to service semantics. HNS has its own requirements/limitations and should not be assumed to be enabled on every bucket.

When designing an application, determine whether the bucket uses a flat namespace or HNS; do not rely on the Console UI to infer this. An application that only stores objects by key/prefix usually does not need real folder resources.

### 4.3. Designing Object Names

An object name can be organized by business domain:

~~~text
receipts/{tenantId}/{yyyy}/{MM}/{documentId}.pdf
avatars/{userId}/{version}.webp
exports/{jobId}/result.csv
events/{yyyy}/{MM}/{dd}/{eventId}.json
~~~

Recommendations:

1. Use stable identifiers such as UUIDs or business IDs instead of user-provided filenames as the primary identifier.
2. Choose prefixes that support querying, access control, lifecycle rules, and data cleanup.
3. Do not include emails, phone numbers, access tokens, secrets, or sensitive data in object names.
4. Normalize characters, spaces, and Unicode if names are passed into URLs, logs, or other systems.
5. Avoid conventions that make it hard to distinguish between **a/b**, **a//b**, **a/../b**, and similar strings; GCS does not automatically sanitize object names into safe filesystem paths.
6. Do not use object names as an authorization mechanism. IAM and policies are the access control layer.

Object names have length limits and character rules defined by Cloud Storage; if the system accepts names from users, validate and properly encode them when passing through URLs/HTTP. Do not concatenate user input directly into URLs or local file paths.

### 4.4. Prefixes Support Listing and Organization, Not IAM Replacement

Suppose a bucket contains:

~~~text
receipts/tenant-a/2026/receipt-001.pdf
receipts/tenant-a/2026/receipt-002.pdf
receipts/tenant-b/2026/receipt-003.pdf
~~~

The application can list objects with the prefix **receipts/tenant-a/**. However, if IAM grants read access to the entire bucket, a prefix in application code is not a security boundary. To isolate tenants, design appropriate IAM conditions/authorization, bucket/project separation, or a trusted authorization adapter; do not rely on a client passing its own prefix.

## 5. Generation: Data Version of an Object

**Generation** is a value assigned by Cloud Storage to a data version of an object. When creating an object or replacing an object's content, GCS creates a new generation. Generation identifies the exact byte version being referenced.

Illustrative example:

| Time | Operation | Generation |
| --- | --- | --- |
| T1 | Create **reports/summary.csv** with content A | **1001** |
| T2 | Overwrite the same object name with content B | **1002** |
| T3 | Overwrite again with content C | **1003** |

The numbers above are illustrative only; actual generations are issued by GCS. **Do not generate generations yourself** and do not interpret a generation as a timestamp. Treat it as a version identifier used for comparison and preconditions.

### 5.1. Generation Differs from Object Name

Object name answers: "Which object in the bucket are we referring to?"

Generation answers: "Which data version of that object are we referring to?"

One object name can go through many generations over time. When an application stores only the bucket and object name, it usually points to the **live version** at request time. If the business logic needs to re-read the exact content that was processed, store the corresponding generation or use an appropriate versioning/audit mechanism.

### 5.2. When Does Generation Change?

- Creating a new object: GCS assigns a generation to the object.
- Replacing the content of an object with the same name: a new generation is assigned.
- Updating only the metadata of the same data version: generation does not change; metageneration changes.
- Deleting an object: the generation of the deleted version does not become a new data generation; recovery behavior depends on Object Versioning, soft delete, retention, and related policies.

Do not use generation as a business counter or a system-wide event sequence. It belongs to the object lifecycle within GCS.

## 6. Metageneration: Metadata Version

**Metageneration** identifies the metadata version of a generation. When an object's metadata is updated, metageneration changes; the object's bytes do not necessarily change.

Example:

| Operation | Generation | Metageneration |
| --- | --- | --- |
| Upload a new object | **1001** | **1** (illustrative) |
| Change Content-Type | **1001** | **2** |
| Add custom metadata reviewed=true | **1001** | **3** |
| Overwrite object data | **1002** | new metadata version |

The specific values in the table are illustrative. Rules to remember:

- **Generation** is tied to the data version.
- **Metageneration** is tied to the metadata version of that generation.
- Updating metadata does not create a new object data generation.
- When a new data generation appears, the metadata of the new generation also enters a new lifecycle.

Metageneration is very useful when multiple services update metadata concurrently. For example, worker A adds **classification=approved**, while worker B simultaneously modifies **reviewer=team-2**. Without a precondition, one metadata write can overwrite the other's changes depending on how the update is performed. Use **ifMetagenerationMatch** to update only if the metadata is still at the version the worker read.

## 7. Object Versioning, Soft Delete, and Retention

### 7.1. Object Versioning

When **Object Versioning** is enabled on a bucket, replacing or deleting a live object can preserve the old version as a **noncurrent version** instead of removing it immediately. Versions are distinguished by generation.

Example:

~~~text
Object name: reports/summary.csv

Live generation:       1003  (content C)
Noncurrent generation: 1002  (content B)
Noncurrent generation: 1001  (content A)
~~~

Applications can reference a specific version via generation when supported by the API/SDK. Retaining many versions increases storage usage and cost; design lifecycle rules to delete noncurrent versions after an appropriate period.

**Object Versioning is not a complete backup.** It does not replace controlling bucket deletion permissions, protecting accounts, strategic replication/backup, retention policies, or recovery procedures. Principals with permission to delete versions and lifecycle rules can still remove data.

### 7.2. Soft Delete

Cloud Storage provides a **soft delete** mechanism to retain deleted objects for a configured retention period. This is a separate concept from Object Versioning. A bucket can have versioning and soft delete enabled according to supported configurations, but you must understand the two different retention and recovery mechanisms.

Do not assume every bucket has the same default retention; verify the actual bucket configuration and organization policies. Once the soft delete period expires or an object is permanently deleted under the corresponding mechanism, recovery is no longer possible.

### 7.3. Retention Policy and Bucket Lock

A retention policy sets the minimum duration an object must be kept before it can be deleted/modified according to rules. **Bucket Lock** can lock a retention policy so that the policy cannot be reduced or removed once locked. This choice has major implications for data governance; review legal requirements, lifecycle, costs, and procedures before applying it.

Three concepts to separate:

| Mechanism | What does it protect? | Considerations |
| --- | --- | --- |
| Object Versioning | Preserves old generations when an object is replaced/deleted per versioning semantics | Consumes storage; requires lifecycle cleanup |
| Soft delete | Retains deleted objects for a configured retention period | Time-limited; distinct from noncurrent versions |
| Retention policy / Bucket Lock | Prevents deletion/modification before the mandatory retention period | Hard to change after locking; requires governance decision |

## 8. Preconditions: Writing Data Safely Under Concurrent Service Access

A system with multiple workers may create or update objects concurrently. If all of them write without checking the current version, there is a risk of **lost updates**: a valid change gets overwritten by another request.

Cloud Storage supports generation and metageneration preconditions to protect operations in a compare-and-set manner.

### 8.1. ifGenerationMatch

The condition **ifGenerationMatch=N** requires the current generation to equal N before the operation is executed.

- **ifGenerationMatch=0:** succeeds only if there is currently no live object with that name.
- **ifGenerationMatch=1001:** succeeds only if the live generation is still 1001.
- If the condition does not match, the request fails with a precondition error (typically HTTP 412).

Business example: two workers both read object generation 1001. Worker A successfully writes new content, creating generation 1002. Worker B still sends a request with **ifGenerationMatch=1001**; B's request is rejected instead of silently overwriting A's new data.

### 8.2. ifMetagenerationMatch

Used when updating metadata without wanting another service's changes to be overwritten:

- Read the object with metageneration 3.
- Build the new metadata based on the data just read.
- Update only if **ifMetagenerationMatch=3**.
- If another service has modified the metadata to metageneration 4, the request fails and you need to re-read and merge.

### 8.3. Creating an Object Only If It Does Not Yet Exist

An upload that must ensure it does not overwrite an existing object can use the precondition **ifGenerationMatch=0**. This prevents name collisions and overwrites in race conditions; merely checking "object does not exist" in the application and then uploading afterward is **unsafe** because another worker may create the object between the two steps.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant G as Cloud Storage
    participant B as Worker B
    A->>G: Upload key X, ifGenerationMatch=0
    G-->>A: Success, generation 1001
    B->>G: Upload key X, ifGenerationMatch=0
    G-->>B: Precondition Failed (412)
    Note over A,B: B does not overwrite A's object
~~~

### 8.4. When a Precondition Fails

Do not treat every HTTP 412 as a system error to retry immediately. It may be a **business conflict**. The application should:

1. Re-read the latest object/generation/metageneration if permitted.
2. Decide whether to merge, create a different object name, or ask the user to resolve it.
3. If retrying, construct the request with the new precondition after evaluating business logic.
4. Log the necessary generation/metageneration and request ID without logging sensitive data.

## 9. Metadata: Describing Objects and How to Use It

### 9.1. System Metadata

Cloud Storage manages system fields such as:

| Field | Meaning | Example |
| --- | --- | --- |
| Content-Type | MIME type of the content | application/pdf |
| Cache-Control | Caching behavior | private, max-age=3600 |
| Content-Disposition | How the browser handles the content | attachment; filename="report.pdf" |
| Content-Encoding | Encoding type of the object | gzip |
| Content-Language | Content language | vi |
| Storage class | Object storage class | STANDARD |
| Size | Size in bytes | 1048576 |
| Time created / updated | Creation/update timestamps per API | timestamp |
| CRC32C / MD5 hash | Checksums for integrity verification | checksum value |
| Generation / Metageneration | Data/metadata version | generation number |

Not all fields can be freely set by the application. Some fields are computed or managed by GCS, while others can be set when creating/updating an object. Read the specific API documentation before building a generic adapter.

### 9.2. Custom Metadata

Applications can attach custom key-value pairs, for example:

~~~json
{
  "document-id": "doc-2026-001",
  "tenant-id": "tenant-a",
  "classification": "internal",
  "source-system": "document-api"
}
~~~

In Cloud Storage, custom metadata is represented as a string key/value map. For example, in Java you can pass a **Map<String, String>** via **BlobInfo.Builder.setMetadata(...)**.

Custom metadata is suitable for small attributes used to look up or process an object, not for storing full business payloads, large JSON blobs, or secrets. Choose stable key names, namespace them when multiple teams share a bucket, and standardize update rules.

### 9.3. Metadata Does Not Replace a Database

Do not use custom metadata as a store for complex queries:

- GCS is not a relational database for arbitrary queries across any metadata key.
- Listing objects by prefix differs from searching by a custom metadata field.
- Metadata updates can cause contention and require preconditions.
- Metadata has size limits and can be read by any principal permitted to read object metadata.

If you need to search by tenantId, approval status, owner, or business timestamp, consider a separate database/index; metadata is only supplementary information attached to the object.

### 9.4. Content-Type and Cache-Control Affect Delivery

If you upload a PDF without setting Content-Type, downstream clients may receive unexpected metadata. If an object contains private data but has `Cache-Control: public, max-age=...`, intermediate caches may store the content in a way that violates security policies.

Choose Content-Type based on validated content, not solely on the file extension supplied by the user. For sensitive documents, design appropriate cache/disposition headers and access mechanisms (such as time-limited signed URLs).

## 10. Generation, ETag, and Checksums: Do Not Confuse Them

| Value | Purpose | Should it be used as a version token? |
| --- | --- | --- |
| Generation | Identifies the data version of an object | **Yes**, with appropriate preconditions |
| Metageneration | Identifies the metadata version | **Yes**, when protecting metadata updates |
| ETag | Validator value provided by the API | Do not assume by default that it equals generation or MD5 |
| CRC32C / MD5 | Verifies data integrity as supported by the API | Use for checksums, not as a replacement for generation |

ETag can be useful in requests with appropriate conditional headers, but you should not assume ETag is always the MD5 of the bytes. With multipart/composite objects or certain encryption modes, the relationship between ETag and MD5 may not match assumptions. If you need to verify data integrity, use the checksums supported by Cloud Storage/the client library and understand their semantics.

## 11. IAM and Bucket/Object Access Control Models

Cloud Storage supports IAM at the project/bucket level and may have ACLs under the legacy model. For new designs, generally prefer **Uniform bucket-level access (UBLA)** to manage permissions through IAM instead of mixing object/bucket ACLs.

Common predefined roles:

| Role | General capability scope | Example scenario |
| --- | --- | --- |
| roles/storage.objectViewer | Read objects and metadata within the granted scope | Service that only downloads documents |
| roles/storage.objectCreator | Create objects; does not implicitly grant read/delete/overwrite on existing objects | Service receiving new uploads |
| roles/storage.objectUser | Broader set of object operations, as defined by the role | Application needing to create/read/update/delete objects |
| roles/storage.objectAdmin | Administer objects within the granted scope | Operations/data cleanup tools |
| roles/storage.admin | Broad administration of buckets/objects and Storage configuration per the role | Infrastructure administrators |

Specific roles must be assigned at the proper resource scope. Do not grant **roles/storage.admin** to a runtime service simply because it needs to upload files. If read/write separation is needed, create custom roles or use appropriate predefined roles.

**Public access prevention** helps prevent unintended public grants; **UBLA** removes ACLs from the management path. They solve different problems and can be used together according to security requirements. Do not enable public access just to quickly test downloading a file; use an authorized principal or a time-limited signed URL when appropriate.

### 11.1. A Signed URL Is Not a Public Bucket

A signed URL is a URL carrying a signature and expiration time for a specific operation/resource. Anyone possessing the URL can perform the signed operation during its validity window under supported conditions; therefore, the URL must be treated like a bearer token and not logged or shared publicly.

Signed URLs do not replace overall IAM, nor do they make the bucket public. The application must control who is allowed to request URL generation, the expiration duration, HTTP method, and object key.

## 12. Hands-On: Creating a Bucket and Uploading Objects with gcloud

### 12.1. Selecting Project and Location

Before creating a bucket, confirm the current project:

~~~bash
gcloud config get-value project
gcloud projects describe PROJECT_ID
~~~

Create a bucket in a suitable region, for example:

~~~bash
gcloud storage buckets create gs://training-documents-dev \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access
~~~

**training-documents-dev** and **PROJECT_ID** are placeholders. The bucket name must be unique in the GCS namespace and valid under current naming rules. Creating a bucket is a provisioning operation; run it only in a dev project where you have been granted permission.

### 12.2. Uploading an Object with a Prefix

~~~bash
gcloud storage cp ./sample.pdf \
  gs://training-documents-dev/reports/2026/sample.pdf
~~~

After uploading, the object name is **reports/2026/sample.pdf**. The prefix **reports/2026/** groups objects; with a flat namespace, it is not necessarily a folder resource.

### 12.3. Viewing Metadata and Generation

~~~bash
gcloud storage objects describe \
  gs://training-documents-dev/reports/2026/sample.pdf
~~~

The describe command may return information such as bucket, name, generation, metageneration, contentType, size, checksums, storageClass, and timestamps depending on the CLI version/output. Use this output to record the actual generation rather than assuming a value.

### 12.4. Updating Custom Metadata

Example with a CLI supporting custom metadata update flags:

~~~bash
gcloud storage objects update \
  gs://training-documents-dev/reports/2026/sample.pdf \
  --update-custom-metadata=classification=internal,source=training
~~~

Flag syntax and capabilities may vary by gcloud version; check **gcloud storage objects update --help** for your installed CLI. After updating, inspect object describe again to observe the metadata and metageneration. Do not place secrets or sensitive data in custom metadata.

### 12.5. Enabling Object Versioning

~~~bash
gcloud storage buckets update \
  gs://training-documents-dev \
  --versioning
~~~

After enabling, overwrite an object with the same name and inspect the generations. Versioning can increase storage volume and costs; combine it with lifecycle rules for noncurrent versions according to retention policies. Before modifying a production bucket, review retention, soft delete, and data governance rules.

## 13. Java/Spring Boot Integration with Google Cloud Storage

### 13.1. Client Library and Spring Integration

The official Java client typically uses these artifacts:

- **com.google.cloud:google-cloud-storage** for the Cloud Storage Java client.
- Spring Cloud GCP/Google Cloud Spring integration starter (if used) to bring configuration and beans into Spring Boot.
- The corresponding BOM to manage versions of GCP/Spring libraries.

Artifacts and versions must match the project's Spring Boot/Java baseline. Do not pick the latest version independently if the project's BOM or Spring Cloud release train manages other libraries.

### 13.2. Application Default Credentials (ADC)

The Cloud Storage Java client typically uses **Application Default Credentials (ADC)** when creating the service:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

ADC is a mechanism for discovering identity from the environment. In local development, developers can set up ADC via **gcloud auth application-default login** per organization policy. When running on Google Cloud, workloads should use an attached service account or appropriate Workload Identity/Workload Identity Federation instead of embedding long-lived service account keys into images.

Distinguish between:

- **gcloud auth login:** logs in to run gcloud commands as a user account.
- **gcloud auth application-default login:** creates credentials for applications using ADC locally.
- **Service account/workload identity:** identity for workloads in deployed environments.

Successfully logging in to gcloud does not automatically prove that the Java process has valid ADC or permissions on the bucket. Verify the actual credential source and principal.

### 13.3. Creating a Storage Bean in Spring

If the Spring Cloud GCP/Google Cloud Spring starter for your project version already auto-configures a **Storage** bean, you can inject that bean. If you do not use the starter or need manual control, you can declare:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GoogleCloudStorageConfiguration {

    @Bean
    Storage googleCloudStorage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

In real applications, check auto-configuration conditions to avoid creating two competing Storage beans. If separate projects/credentials are needed for multiple environments, explicitly configure StorageOptions per environment and manage the client lifecycle according to library guidance.

### 13.4. Uploading an Object with Content Type and Custom Metadata

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class DocumentObjectStore {

    private final Storage storage;

    public DocumentObjectStore(Storage storage) {
        this.storage = storage;
    }

    public long uploadText(String bucket, String objectName, String text) {
        BlobInfo info = BlobInfo.newBuilder(
                        BlobId.of(bucket, objectName))
                .setContentType("text/plain; charset=utf-8")
                .setCacheControl("private, max-age=0")
                .setMetadata(Map.of(
                        "source-system", "document-api",
                        "classification", "internal"))
                .build();

        Blob created = storage.create(
                info,
                text.getBytes(StandardCharsets.UTF_8),
                Storage.BlobTargetOption.doesNotExist());

        return created.getGeneration();
    }
}
~~~

**doesNotExist()** applies a precondition to create the object only if no live object with the same name exists. If the object already exists, the operation fails instead of silently overwriting. In the application, translate precondition errors into clear business outcomes (e.g., conflict/duplicate) and do not retry by dropping the precondition.

The example uses a small payload as a byte array. For large files, evaluate streaming, resumable uploads, multipart/parallel composite uploads if appropriate, memory footprint, retries, and checksums; do not read an entire large file into heap just to call a convenience overload.

### 13.5. Reading an Object and Generation

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public class DocumentObjectReader {

    private final Storage storage;

    public DocumentObjectReader(Storage storage) {
        this.storage = storage;
    }

    public Blob describe(String bucket, String objectName) {
        Blob blob = storage.get(BlobId.of(bucket, objectName));
        if (blob == null) {
            throw new IllegalArgumentException("Object does not exist");
        }
        return blob;
    }

    public long currentGeneration(String bucket, String objectName) {
        return describe(bucket, objectName).getGeneration();
    }
}
~~~

**Storage.get(BlobId)** reads object metadata; byte content can be downloaded separately via the appropriate API. If a specific generation is required, use the BlobId/API option with the corresponding generation supported by your client library version, rather than passing only the object name and assuming the live object has not changed.

### 13.6. Updating Metadata with a Precondition

As a Java API example, read metadata first and then update based on the current metageneration:

~~~java
Blob current = storage.get(BlobId.of(bucket, objectName));
if (current == null) {
    throw new IllegalArgumentException("Object does not exist");
}

BlobInfo changed = current.toBuilder()
        .setMetadata(Map.of(
                "classification", "reviewed",
                "reviewed-by", "quality-service"))
        .build();

Blob updated = storage.update(
        changed,
        Storage.BlobTargetOption.metagenerationMatch(
                current.getMetageneration()));
~~~

If another service updated the metadata between the read and the update, the precondition does not match and the request is rejected. The application needs to re-read and merge metadata according to business logic, without removing the condition just to force the write to succeed.

## 14. Organizing Adapters Around Business Boundaries

A Spring Boot service should not let controllers or domain models depend directly on **Blob**, **BlobInfo**, or Google Cloud SDK details. Separating an interface makes it easier to swap providers or test:

~~~java
public interface DocumentStorage {
    StoredDocument save(String documentId, byte[] content, String contentType);
    StoredDocument describe(String documentId);
}

public record StoredDocument(
        String bucket,
        String objectName,
        long generation,
        long metageneration,
        String contentType,
        long size) {}
~~~

The GCS adapter is responsible for:

- Converting documentId into an object name by convention.
- Building BlobInfo with content type/metadata.
- Uploading with the appropriate generation precondition.
- Reading generation/metageneration and mapping to the application model.
- Translating SDK exceptions into adapter-layer errors.
- Avoiding exposing bucket names, credentials, or sensitive metadata in APIs unless needed.

Another adapter can use Amazon S3 or Azure Blob Storage. The business interface should describe required behavior, such as **saveDocument**, **loadDocument**, **deleteDocument**, **getVersion**, instead of trying to build a generic API covering every object storage difference.

## 15. Testing Buckets, Generation, and Metadata

### 15.1. Unit Tests

Mock the DocumentStorage interface to test business logic, object name validation, document ID mapping, duplicate error handling, and idempotency. Unit tests do not require ADC or a real GCP project.

### 15.2. Integration Tests on a Dedicated GCP Project

A real integration test should use a test project, a dedicated bucket, a least-privilege IAM service account, and explicit cleanup:

1. Create a bucket in a test location following approved infrastructure procedures.
2. Grant permissions to the test identity on that specific bucket.
3. Upload an object with **ifGenerationMatch=0**.
4. Read the object and verify bytes, content type, custom metadata, and generation.
5. Update metadata with **ifMetagenerationMatch**.
6. Overwrite with the matching **ifGenerationMatch**; then retry with the old generation and expect a precondition failure.
7. If versioning is enabled, verify noncurrent generations per configuration.
8. Clean up objects and buckets according to test policy; do not delete shared resources belonging to other teams.

Do not use a production project for generation/versioning tests because tests can create versions, incur storage costs, or alter metadata unintentionally.

### 15.3. Important Error Tests

| Scenario | Expectation |
| --- | --- |
| Create object with **doesNotExist()** when object already exists | Conflict/precondition failure, no overwrite |
| Update metadata with stale metageneration | Precondition failure, newer metadata is preserved |
| Read non-existent object name | Clear not-found result |
| Principal lacks **storage.objects.get** | Permission denied |
| Incorrect bucket location/config | Detected from configuration/resource, no infinite retries |
| Object replaced during processing | Generation precondition prevents operating on an unexpected version |
| Metadata contains sensitive field | Validation/masking test rejects or strips disallowed fields |

### 15.4. Testing Does Not Mean a Local Emulator

Some GCP services have emulators, but **you must not assume Cloud Storage always has an official emulator equivalent to all production behaviors**. When using a third-party fake server or emulator, clearly verify supported APIs and limitations. For critical features such as IAM, generation preconditions, retention, soft delete, versioning, and signed URLs, run integration tests on a dedicated GCP project to verify real semantics.

## 16. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| **storage.get(...)** returns null | Wrong bucket/object name or object does not exist | Verify bucket, object name, and generation |
| **403 Forbidden** | ADC principal lacks IAM permission or blocked by policy | Verify principal, project/bucket scope, role, and conditions |
| **401 Unauthorized** | Invalid/expired credentials or wrong token audience/scope | Check ADC/workload identity and system clock |
| Bucket creation reports name already exists | Globally unique bucket name is already used by another project | Choose another name; do not assume names are only unique within a project |
| Accidental object overwrite | Missing generation precondition or non-unique object naming logic | Use ifGenerationMatch and stable IDs |
| Metadata lost after update | Sent a new metadata map instead of merging existing keys | Read metadata, merge keys, and use metageneration precondition |
| Read wrong old/new content | Stored only object name without generation | Record generation during processing and read the exact version |
| Folder not visible in console | Prefix has no objects yet or using flat namespace | List by prefix; do not treat folder markers as mandatory |
| Java uses different ADC than gcloud CLI | Logged into gcloud user account without creating ADC or different workload identity | Check ADC source and the Java process principal |
| Out-of-memory on large upload | Loaded entire file into a byte array | Use streaming/resumable upload and resource limits |

When investigating 403 errors, do not rush to grant **roles/storage.admin**. Identify which API requires which permission, which principal is calling, which bucket/project is targeted, and which policies/conditions apply.

## 17. Comprehensive Hands-On Exercise

**Scenario:** A Spring Boot application manages contract documents. Each tenant has its own prefix in the **training-contracts-dev** bucket. Upon successful upload, the system saves bucket, objectName, generation, metageneration, contentType, and size into a database. Another worker adds custom metadata **review-status** after inspecting the content.

### Task A — Design Bucket and Object Names

1. Propose a location and storage class for frequently accessed contract data.
2. Define an object name convention containing tenant, year/month, and document ID.
3. Explain why prefixes do not automatically provide tenant isolation permissions.
4. Choose UBLA, Public Access Prevention, and appropriate IAM roles.
5. State when Object Versioning, soft delete, or retention policies should be enabled.

### Task B — Generation and Concurrency

1. The upload API must create a new object without overwriting; use **ifGenerationMatch=0**.
2. The worker reads object generation G1 and updates metadata with **ifMetagenerationMatch=M1**.
3. Suppose another worker updates metadata first, incrementing metageneration to M2. Explain why the first request is rejected and how to merge again.
4. Explain why generation differs from metageneration, and why ETag is not an MD5 by default.
5. If the system needs to re-download the exact approved content, what additional value must it store besides the object name?

### Task C — Java/Spring Implementation

1. Create a Storage bean via ADC or use the bean auto-configured by Spring Cloud GCP.
2. Write a DocumentStorage adapter to upload and return the generation.
3. Write the flow to read metadata and update with a precondition.
4. Do not put secrets in custom metadata; identify which fields belong in the database instead.
5. Design mapping precondition errors to business conflicts instead of unconditional retries.

### Task D — Testing and Operations

- Unit test object name validation and conflict handling logic.
- Integration test with a dedicated GCP project/bucket and a restricted IAM service account.
- Test generation mismatch, metageneration mismatch, versioning, and metadata merge.
- Monitor 403, 412, not found errors, latency, size, and checksums.
- Design lifecycle rules for noncurrent versions if versioning is enabled.
- Review storage and retrieval costs by storage class.

**Pass criteria:** Learners can distinguish bucket from object name, generation from metageneration, and system metadata from custom metadata; know how to use preconditions to prevent lost updates; and have an IAM/testing design suited for multi-tenant applications.

## 18. Comparison with AWS S3 and Azure Blob Storage

All three platforms provide object storage, but their semantics and APIs are not identical:

| Aspect | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Container | Bucket | Bucket | Storage account + container |
| Object identifier | Object name | Object key | Blob name |
| Version identifier | Generation | Version ID when versioning is enabled | Version ID when versioning is enabled |
| Metadata concurrency | Metageneration/precondition | Conditional requests/ETag and corresponding APIs | ETag/lease/conditional headers |
| Custom metadata | Key/value map | User-defined metadata | Blob metadata |
| Access control | IAM, UBLA, ACL per configuration | IAM, bucket/access point policy, ACL per configuration | Azure RBAC, SAS, access policy per model |
| Java integration | Google Cloud Storage Java client / Spring Cloud GCP | AWS SDK v2 / Spring Cloud AWS | Azure SDK / Spring Cloud Azure |

Do not build a multi-cloud abstraction assuming generation, S3 Version ID, and Azure Blob Version ID share the same format or lifecycle. The business interface should standardize the behaviors the application needs; each provider adapter is responsible for mapping version tokens, metadata, and preconditions to its specific API.

## 19. Key Takeaways

- **Bucket** defines the container, project, location, access configuration, and storage lifecycle.
- **Object name** is the object identifier. With a flat namespace, `/` is usually just a prefix convention; HNS is a separate structural option.
- **Generation** identifies the data version; **metageneration** identifies the metadata version.
- **Object Versioning**, **soft delete**, and **retention policy** are distinct mechanisms requiring cost and recovery policy evaluation.
- **Metadata** describes objects; system metadata and custom metadata serve different purposes. Do not store secrets or complex query data in custom metadata.
- **Generation/metageneration preconditions** help prevent overwrites and lost updates when multiple services operate concurrently.
- Spring Boot can use the Google Cloud Storage Java client with ADC or appropriate Spring Cloud GCP integration; IAM and workload identity still need to be configured separately.

Mastering these concepts helps Spring Boot applications store objects in a structured way, clearly control versions and metadata, reduce data overwrite risks, and establish a foundation for comparing and building adapters for AWS S3 and Azure Blob Storage.

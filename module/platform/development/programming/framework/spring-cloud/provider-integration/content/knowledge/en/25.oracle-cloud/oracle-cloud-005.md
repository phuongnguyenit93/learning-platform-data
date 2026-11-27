# Integrating OCI Object Storage with Spring Resources

Oracle Cloud Infrastructure (OCI) Object Storage stores files and unstructured data as objects inside buckets. With Spring Boot, you can interact with it through the Spring Cloud Oracle API or use the Spring `Resource` abstraction to read and write objects just like familiar resources. Both approaches use the OCI authentication and IAM policies configured for your application.

Spring Cloud Oracle 2.0.4 provides the Object Storage starter, which auto-configures a `Storage` bean and registers a protocol resolver to turn Object Storage URIs into Spring `Resource` instances. Since version 2.0.1, this resource also implements `WritableResource`, allowing applications to upload via `OutputStream`. When specialized features are needed—such as paginated object listing, multipart uploads, or creating pre-authenticated requests (PARs)—you can obtain the OCI Java SDK client exposed by the `Storage` bean.

This lesson uses `document-service` as the running example. The service stores PDF contracts in the `contracts-prod` bucket, creates metadata, reads files back for users, issues time-limited upload/download URLs for partners, and manages objects under IAM policies. The goal is to ensure the application accesses only its designated buckets/objects, streams data without loading large files entirely into the heap, and maintains retryability, auditing, and testability.

## 1. Learning Objectives and Architecture

After this lesson, you can:

1. Describe namespaces, buckets, objects, compartments, and regions in OCI Object Storage.
2. Choose between the Spring Cloud Oracle `Storage` API, Spring `Resource`, and the OCI Java SDK.
3. Add the Object Storage starter and configure authentication/region/compartment in Spring Boot.
4. Use the `Storage` bean to upload, download, store JSON POJOs, and delete objects.
5. Use `ResourceLoader` to resolve an OCI object URL into a `Resource` or `WritableResource`.
6. Build REST endpoints that stream files without loading entire objects into memory.
7. Use the OCI SDK to list objects, handle pagination, and inspect metadata.
8. Upload large files using `UploadManager` and multipart upload.
9. Create, distribute, and revoke pre-authenticated requests following least privilege.
10. Configure IAM policies for workloads and buckets.
11. Handle ETags, conditional writes, versioning, retries, timeouts, and authorization errors.
12. Write unit and integration tests for upload/download flows, permissions, and shared URLs.

~~~mermaid
flowchart TD
    A["Browser / API client"] --> B["Spring Boot document-service"]
    B --> C["Authentication provider"]
    C --> D["OCI IAM principal"]
    D --> E["IAM policy"]
    B --> F["Storage bean"]
    B --> G["Spring Resource / WritableResource"]
    F --> H["OCI Java SDK ObjectStorageClient"]
    G --> H
    H --> I["OCI Object Storage endpoint"]
    I --> J["Bucket contracts-prod"]
    J --> K["Objects: tenant/document/version"]
    B --> L["Audit + metadata database"]
~~~

Spring abstractions do not replace OCI IAM. The resource URL locates the object; the identity provider signs the request; IAM policies still decide whether the application is permitted to read or write that object.

## 2. The OCI Object Storage Model

### 2.1. Namespace, Bucket, and Object

Object Storage has three core concepts:

- **Namespace:** a tenancy-level namespace acting as the top-level container for buckets and objects. OCI assigns one unique namespace per tenancy and does not allow renaming it.
- **Bucket:** a logical container residing in one region and one compartment. A bucket holds objects and carries policies, encryption, versioning, lifecycle, and retention settings.
- **Object:** data content plus metadata. An object is identified by its bucket and object name.

The namespace stays the same when accessing different regions within the same tenancy; endpoints and bucket resources remain bound to a region. Bucket names must be unique within their respective namespace/region. A bucket belongs to a single compartment.

You can retrieve the namespace via the OCI Console, CLI, or `GetNamespace` API. The Spring Cloud Oracle `Storage` bean provides `getNamespaceName()` to retrieve the current tenancy's namespace. A namespace is neither a compartment OCID nor a bucket name.

### 2.2. Object Names and Simulated Directories

Object Storage has no physical directories like a filesystem. An object name is a flat key string; forward slashes are commonly used to simulate prefixes/hierarchies:

~~~text
contracts/
  tenant-001/
    2026/
      contract-1001.pdf
      contract-1002.pdf
  tenant-002/
    2026/
      contract-2001.pdf
~~~

These names are actually object keys such as `contracts/tenant-001/2026/contract-1001.pdf`. Prefixes and delimiters help list items by group, but they do not create separate folder resources.

Object key rules:

- Generate keys on the server; never trust arbitrary client-supplied paths.
- Use verified tenant IDs, document IDs, or UUIDs as key segments.
- Avoid putting personal data, card numbers, emails, or secrets in object names.
- Normalize Unicode and path separators per application conventions.
- Constrain length and characters so URLs and SDKs handle them consistently.
- Never concatenate user-supplied filenames directly into object keys without validation.
- Use separate prefixes for quarantine, temporary, processed, and archive areas if the business requires it.

### 2.3. Region and Endpoint

Object Storage is a regional service. Endpoints follow the pattern:

~~~text
https://objectstorage.<region>.oraclecloud.com
~~~

Example region identifiers:

~~~text
ap-singapore-1
ap-tokyo-1
us-ashburn-1
eu-frankfurt-1
~~~

The bucket's region must match the region endpoint used by the SDK client. Sending requests to the wrong region can cause redirects, "resource not found" errors, or confusing authorization errors.

Spring Cloud Oracle uses `spring.cloud.oci.region.static` to set the region for API calls. This value takes precedence over the region in the OCI auth configuration file or `spring.cloud.oci.config.region`.

### 2.4. Bucket and Compartment

A bucket is created inside a compartment. IAM policies on the compartment determine which workloads can create buckets, read objects, write objects, list items, or delete data.

Common layout:

~~~text
Tenancy
└── Production
    ├── AppRuntime
    │   └── document-service
    ├── AppData
    │   └── contracts-prod
    └── Security
        └── audit and key resources
~~~

The runtime workload lives in `AppRuntime`; the bucket lives in `AppData`. Dynamic groups or OKE workload identities are granted permissions on `AppData`. Simply running a service in `AppRuntime` does not grant it access to `AppData`.

### 2.5. Strong Consistency

OCI Object Storage provides strong consistency: once a write succeeds, subsequent read requests return the latest version of the data. This lets upload-then-download flows verify immediately.

Strong consistency does not eliminate the need to handle concurrency. Two simultaneous PUT requests can still overwrite the same object key unless conditional requests or distinct keys are used.

### 2.6. Object Storage vs. Filesystem

| Characteristic | Filesystem | OCI Object Storage |
| --- | --- | --- |
| Identifier | Path | Bucket + object name |
| Folder | Directory resource | Prefix inside object name |
| Read/write | File handle | HTTP API/SDK stream |
| Rename | Usually a filesystem operation | Typically copy-then-delete or rename API where supported |
| Locking | File lock | ETag, conditional request, or business-level lock |
| Metadata | File attributes | HTTP metadata and `opc-meta` |
| Location | Disk/mount | Bucket region |
| Access control | OS permissions | OCI IAM policies and credentials |

Do not call `getFile()` on an Object Storage `Resource` expecting a local file. Use `getInputStream()` or `WritableResource.getOutputStream()`.

## 3. Choosing the Right API in Spring

### 3.1. Spring Cloud Oracle Storage API

The `Storage` API provides application-level operations:

- `createBucket(bucketName)` or `createBucket(bucketName, compartmentId)`.
- `upload(bucketName, key, inputStream, metadata)`.
- `download(bucketName, key)`.
- `download(bucketName, key, version)`.
- `store(bucketName, key, object)` to save a POJO as JSON.
- `read(bucketName, key, clazz)` to read JSON into a POJO.
- `deleteObject(bucketName, key)`.
- `deleteBucket(bucketName)`.
- `getNamespaceName()` and `getClient()`.

The starter automatically registers a `Storage` bean in the Spring context. This is the default choice for standard upload/download flows and file operations in services.

### 3.2. Spring Resource Abstraction

Spring `Resource` is a unified abstraction for sources like classpath, filesystem, URLs, and servlet contexts. Spring Cloud Oracle adds a protocol resolver to recognize Object Storage URLs and create `OracleStorageResource` instances.

`Resource` fits well when code expects an `InputStreamSource`/`Resource` to read an object. Starting in Spring Cloud Oracle 2.0.1, Object Storage `Resource` also implements `WritableResource` to write objects.

Benefits:

- Reuses familiar Spring APIs.
- Easy to inject or resolve by URI.
- Can pass a `Resource` into other services that work with files/resources.
- Can use `OutputStream` for uploads.

Limitations:

- `Resource` is not a filesystem file.
- Does not replace APIs for listing buckets/objects, managing PARs, multipart uploads, or version management.
- Object management operations should still use the `Storage` API or OCI SDK.

### 3.3. Direct OCI Java SDK

The `Storage` bean exposes `getClient()`, returning an OCI `ObjectStorageClient`. Use this client when you need APIs not covered by the `Storage` abstraction:

- `ListObjects` and pagination.
- `Create/DeletePreauthenticatedRequest`.
- `UploadManager`/multipart.
- Advanced `GetObject`/`HeadObject`.
- Versioning, retention, lifecycle, replication.
- Conditional requests or specialized API operations.

Do not instantiate a new `ObjectStorageClient` for each HTTP request. Reuse the client configured and lifecycle-managed by the Spring starter.

### 3.4. Quick Selection Table

| Need | API to Use |
| --- | --- |
| Standard file upload | `Storage.upload` |
| Standard file download | `Storage.download` or `Resource` |
| Save JSON POJO | `Storage.store` / `Storage.read` |
| Use object as a Spring dependency | `ResourceLoader` + `Resource` |
| Write via `OutputStream` | `WritableResource` |
| List objects by prefix | OCI SDK `ListObjects` |
| Upload large files | OCI SDK `UploadManager` |
| Create time-limited shared URL | OCI SDK Pre-Authenticated Request |
| Delete object | `Storage.deleteObject` |
| Download older object version | `Storage.download(bucket, key, version)` |

## 4. Adding Dependencies and Spring Boot Configuration

### 4.1. Maven Dependency

Spring Cloud Oracle 2.0.4 provides the starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
    <version>2.0.4</version>
</dependency>
~~~

The starter includes the storage module and required dependencies. Do not add a separate underlying module if the starter already provides it transitively.

Spring Cloud Oracle 2.0.4 upgraded Spring Cloud OCI to Spring Boot 4.1.1 and Spring Framework 7. Before adding the starter to a project using a different Spring Boot version, check the compatibility matrix/release notes and manage versions consistently; do not arbitrarily force different versions of Spring Framework or the OCI SDK.

### 4.2. Gradle Dependency

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-storage:2.0.4")
}
~~~

### 4.3. Local Development Configuration

When developing on a personal machine, use an OCI config file profile:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: C:/Users/developer/.oci/config
      region:
        static: ap-singapore-1
      compartment:
        static: REPLACE_WITH_COMPARTMENT_OCID
      storage:
        enabled: true
~~~

The OCI config file holds the user OCID, tenancy OCID, fingerprint, private key path, and region. Protect the private key with file permissions/passphrase. Never commit config files or PEM keys to Git, and never copy production credentials onto a laptop.

### 4.4. Production Configuration on Compute

When Spring Boot runs on OCI Compute, prefer Instance Principal:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      compartment:
        static: REPLACE_WITH_APPDATA_COMPARTMENT_OCID
      storage:
        enabled: true
~~~

The Compute instance must belong to a dynamic group, and that dynamic group must be granted IAM policies on the compartment holding the bucket. If the principal lacks permission, switching to an API key profile does not fix the root cause; inspect the dynamic group, region, bucket, and policy.

### 4.5. OKE Workload Identity Configuration

With an OKE enhanced cluster, you can use Workload Identity:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: WORKLOAD_IDENTITY
      region:
        static: ap-singapore-1
      compartment:
        static: REPLACE_WITH_APPDATA_COMPARTMENT_OCID
      storage:
        enabled: true
~~~

Policies must bind cluster OCID, namespace, and Kubernetes service account. Do not use a node's API key or a single broad identity shared by every pod in the cluster when workload identity covers the use case.

### 4.6. Supported Auth Types

Spring Cloud Oracle 2.0.4 supports:

| Config Type | Use Case |
| --- | --- |
| `FILE` | OCI config file profile, typically for local development |
| `SIMPLE` | Configuring user OCID, tenancy OCID, fingerprint, and private key via properties |
| `INSTANCE_PRINCIPAL` | OCI Compute |
| `RESOURCE_PRINCIPAL` | OCI Functions/resources supporting resource principal |
| `SESSION_TOKEN` | Short-lived CLI/SDK sessions |
| `WORKLOAD_IDENTITY` | OKE workload identity |

Avoid `SIMPLE` in production when workload identity is available. If a private key must be used, fetch it from a secret manager, restrict read permissions, and schedule rotations.

### 4.7. Default Region and Compartment

Key properties:

| Property | Meaning |
| --- | --- |
| `spring.cloud.oci.config.type` | Authentication type |
| `spring.cloud.oci.config.profile` | Profile in OCI config file |
| `spring.cloud.oci.config.file` | Config file path |
| `spring.cloud.oci.config.region` | Region for auth configuration |
| `spring.cloud.oci.region.static` | Region for API calls; takes precedence over config file |
| `spring.cloud.oci.compartment.static` | Default compartment OCID |
| `spring.cloud.oci.storage.enabled` | Enables/disables the storage module, defaults to `true` |

A default compartment does not mean every operation is automatically permitted in that compartment. IAM policies still govern permissions. When creating buckets in another compartment, use the overload accepting a compartment OCID or configure appropriately.

## 5. Spring Service Structure and the `Storage` Bean

### 5.1. Injecting `Storage`

~~~java
import com.oracle.cloud.spring.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class ContractStorageService {

    private final Storage storage;

    public ContractStorageService(Storage storage) {
        this.storage = storage;
    }
}
~~~

Do not manually instantiate `StorageImpl` or `ObjectStorageClient` inside controllers. The starter auto-configures the `Storage` bean and uses the configured OCI authentication provider.

### 5.2. Retrieving the Namespace

~~~java
public String namespace() {
    return storage.getNamespaceName();
}
~~~

The namespace is assigned at the tenancy level and is not a secret. You can fetch it once during service initialization or call it via the bean as needed. Do not hard-code a namespace from another tenancy into production config.

### 5.3. Provisioning Buckets

Buckets are usually created via IaC or platform provisioning workflows. If the application is responsible for creating buckets in certain environments:

~~~java
import com.oracle.bmc.objectstorage.responses.CreateBucketResponse;

public CreateBucketResponse createBucket(
        String bucketName,
        String compartmentOcid) {

    return storage.createBucket(bucketName, compartmentOcid);
}
~~~

Creating a bucket requires `BUCKET_CREATE`. Do not run this operation on every request or every app restart. If the bucket already exists, handle the conflict by inspecting the existing bucket and verifying expected configuration.

### 5.4. Keeping Bucket Names and Object Keys Out of Client Requests

Controllers receive a document ID or business ID; services look up metadata and determine the bucket/key from verified data. Never let clients submit arbitrary bucket names or read objects belonging to another tenant.

An object key can be generated like this:

~~~java
String objectKey(UUID tenantId, UUID documentId) {
    return "contracts/" + tenantId + "/" + documentId + ".pdf";
}
~~~

This is an example convention. The tenant ID must come from a verified security/business context. If object keys include versions or document types, store the mapping in the database rather than inferring it from client-supplied filenames.

## 6. Uploading Objects with the `Storage` API

### 6.1. Uploading from an `InputStream`

~~~java
import com.oracle.cloud.spring.storage.StorageObjectMetadata;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class ContractUploader {

    private final Storage storage;

    public ContractUploader(Storage storage) {
        this.storage = storage;
    }

    public void uploadPdf(
            String bucketName,
            String objectKey,
            Path sourceFile) throws IOException {

        StorageObjectMetadata metadata =
                StorageObjectMetadata.builder()
                        .contentType("application/pdf")
                        .contentLength(Files.size(sourceFile))
                        .contentDisposition("attachment")
                        .cacheControl("private, no-store")
                        .metadata("document-type", "contract")
                        .build();

        try (InputStream input = Files.newInputStream(sourceFile)) {
            storage.upload(bucketName, objectKey, input, metadata);
        }
    }
}
~~~

`Storage.upload` reads the `InputStream` synchronously. Close the stream after upload completes. Do not use `readAllBytes` for large files, as the entire file would be held on the heap.

`Content-Type` helps clients handle files properly. `Content-Disposition` can request downloading rather than inline rendering. `Cache-Control` suited for private data reduces the risk of caching in intermediaries/browsers. Custom metadata should only contain non-sensitive values.

### 6.2. Uploading from `MultipartFile`

In Spring MVC, `MultipartFile` provides an `InputStream`:

~~~java
import java.io.InputStream;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.multipart.MultipartFile;

@PostMapping(
        value = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Void> upload(
        @RequestPart("file") MultipartFile file,
        @AuthenticationPrincipal Jwt jwt) throws IOException {

    try (InputStream input = file.getInputStream()) {
        documentService.store(
                jwt.getSubject(),
                file.getOriginalFilename(),
                file.getContentType(),
                file.getSize(),
                input);
    }

    return ResponseEntity.accepted().build();
}
~~~

This controller example needs size limits in Spring multipart configuration and at the reverse proxy. Inside the service, validate tenant, file type, size, checksum, and file contents before saving into the production bucket.

Do not trust `Content-Type` or file extensions sent by clients. Use content inspection/malware scanning if required by the business. Unverified files can be uploaded into a quarantine bucket/prefix with restricted access.

### 6.3. Conditional Uploads to Prevent Overwrites

When you only want to create a new object:

~~~java
StorageObjectMetadata metadata =
        StorageObjectMetadata.builder()
                .contentType("application/pdf")
                .contentLength(fileSize)
                .ifNoneMatch("*")
                .build();
~~~

`If-None-Match` with `*` instructs the operation to succeed only if the object does not already exist. If the object is already present, the request is rejected instead of overwriting.

When updating an object based on a previously read ETag, use `If-Match` to avoid overwriting changes made by another request. ETags are for concurrency control; do not treat ETags as the SHA-256 of the payload in all cases, especially with multipart uploads.

### 6.4. Custom Metadata

`StorageObjectMetadata` supports:

- `contentType`.
- `contentLength`.
- `contentDisposition`.
- `contentEncoding`.
- `contentLanguage`.
- `cacheControl`.
- `contentMD5`.
- `ifMatch` and `ifNoneMatch`.
- custom key/value metadata.
- `storageTier`.
- `opcSseKmsKeyId` and related encryption fields.

Never store PII, access tokens, secrets, or contract contents in custom metadata. Metadata frequently appears in API responses/logs/audits and may have broader visibility than the object payload itself.

## 7. Downloading Objects with the `Storage` API

### 7.1. Downloading as a `Resource`

`Storage.download` returns an `OracleStorageResource`, which can be consumed via Spring `Resource`:

~~~java
import org.springframework.core.io.Resource;

public Resource download(
        String bucketName,
        String objectKey) {

    return storage.download(bucketName, objectKey);
}
~~~

Read content via `InputStream`:

~~~java
try (InputStream input = storage.download(bucket, key).getInputStream()) {
    input.transferTo(output);
}
~~~

Close the `InputStream` after use. Do not keep streams open longer than necessary.

### 7.2. Deleting Objects and Downloading Specific Versions

~~~java
public void delete(String bucketName, String objectKey) {
    storage.deleteObject(bucketName, objectKey);
}

public Resource downloadVersion(
        String bucketName,
        String objectKey,
        String versionId) {
    return storage.download(bucketName, objectKey, versionId);
}
~~~

`DeleteObject` requires `OBJECT_DELETE`. If bucket versioning is enabled, check delete marker semantics and object versions before treating a delete operation as permanent deletion. Do not expose a delete endpoint if users only need logical record deletion.

### 7.3. Returning Files via `StreamingResponseBody`

~~~java
import java.io.InputStream;
import java.util.UUID;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@GetMapping("/documents/{documentId}/content")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID documentId) {

    DocumentLocation location =
            documentService.authorizedLocation(documentId);

    Resource resource = storage.download(
            location.bucketName(),
            location.objectKey());

    StreamingResponseBody body = output -> {
        try (InputStream input = resource.getInputStream()) {
            input.transferTo(output);
        }
    };

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_PDF)
            .header(
                    HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                            .filename(location.safeDownloadName())
                            .build()
                            .toString())
            .body(body);
}
~~~

`DocumentLocation` must be constructed only after verifying document read permission and tenant ownership. Never take bucket/key directly from client path/query parameters. Use sanitized filenames to prevent CRLF/header injection.

Streaming avoids loading entire files into the heap. Configure appropriate concurrency limits, timeouts, and thread/executor pools. When a client disconnects, close the stream and stop transferring unnecessary data.

### 7.4. Reading JSON into POJOs

The `Storage` API can store and read Java objects as JSON:

~~~java
public void saveMetadata(
        String bucketName,
        String objectKey,
        DocumentMetadata metadata) throws IOException {

    storage.store(bucketName, objectKey, metadata);
}

public DocumentMetadata loadMetadata(
        String bucketName,
        String objectKey) {

    return storage.read(
            bucketName,
            objectKey,
            DocumentMetadata.class);
}
~~~

Use this feature for small JSON metadata or document manifests. Do not use it to store large binary files or replace a database for relational data, transactions, and complex queries.

## 8. Spring `Resource` and `WritableResource`

### 8.1. Object Storage URI

Spring Cloud Oracle recognizes object URLs structured as:

~~~text
https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<object-name>
~~~

Example:

~~~text
https://objectstorage.ap-singapore-1.oraclecloud.com/n/exampleNamespace/b/contracts-prod/o/contracts/tenant-001/contract-1001.pdf
~~~

This URL is an address locating the object. When resolved by the Spring Cloud Oracle Object Storage protocol resolver, the `Resource` uses the OCI SDK and the application's authentication provider. This URL does not become a public URL or a pre-authenticated URL.

### 8.2. Resolving a `Resource` via `ResourceLoader`

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriUtils;

@Component
public class OciResourceResolver {

    private final ResourceLoader resourceLoader;

    public OciResourceResolver(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource resolve(
            String region,
            String namespace,
            String bucket,
            String objectName) {

        String encodedObject =
                UriUtils.encodePath(objectName, StandardCharsets.UTF_8);

        String uri = "https://objectstorage." + region
                + ".oraclecloud.com/n/" + namespace
                + "/b/" + bucket + "/o/" + encodedObject;

        return resourceLoader.getResource(uri);
    }
}
~~~

`UriUtils.encodePath` encodes necessary characters in the object name while preserving slashes used to represent prefixes. Do not concatenate URL strings from unvalidated input and do not double-encode. For object keys containing special characters, test URI handling on your exact Spring Cloud Oracle version.

### 8.3. Reading a `Resource`

~~~java
Resource resource = resolver.resolve(
        region, namespace, bucket, objectKey);

if (!resource.exists() || !resource.isReadable()) {
    throw new DocumentNotFoundException();
}

try (InputStream input = resource.getInputStream()) {
    input.transferTo(outputStream);
}
~~~

`exists()` or `contentLength()` may trigger requests to Object Storage. Avoid calling them repeatedly within the same request if unnecessary. For remote `Resource` implementations, `isFile()` is normally false and `getFile()` is not the way to read content.

### 8.4. Writing via `WritableResource`

~~~java
import java.io.OutputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.WritableResource;

Resource resource = resolver.resolve(
        region, namespace, bucket, objectKey);

if (!(resource instanceof WritableResource writable)) {
    throw new IllegalStateException(
            "OCI resource does not support writing");
}

try (OutputStream output = writable.getOutputStream()) {
    inputStream.transferTo(output);
}
~~~

The Object Storage `Resource` in Spring Cloud Oracle 2.0.4 implements `WritableResource`. Data is uploaded when the `OutputStream` is closed. Therefore `try-with-resources` not only releases the stream but also completes the write operation.

Do not expose `WritableResource` over a public API letting clients choose arbitrary buckets/keys. The server must determine the target object after authentication and authorization checks.

### 8.5. The URI Resolver Must Be Registered by the Starter

If `spring-cloud-oci-starter-storage` is missing from the classpath or auto-configuration is disabled, Spring's `ResourceLoader` may fall back to resolving the HTTPS URL as a regular `UrlResource`. In that case, requests bypass OCI SDK authentication and may hit 401/403 or attempt unauthenticated public URL access.

Verify:

- The storage starter is declared.
- `spring.cloud.oci.storage.enabled` is not set to `false`.
- Auto-configuration is loaded.
- The URI uses the exact Object Storage host/path format.
- The authentication provider works.
- IAM policies grant permissions on the bucket/object.

### 8.6. When to Choose `Resource` Instead of the `Storage` API?

Use `Resource` when downstream services or libraries already accept `Resource`/`InputStreamSource`/`WritableResource`. Use the `Storage` API when you need bucket operations, upload metadata, version downloads, deletes, or POJO persistence. Use the OCI SDK directly when you need pagination, PARs, multipart, or operations absent from the `Storage` interface.

## 9. Listing Objects and Pagination with the OCI SDK

### 9.1. Why Use the SDK Directly?

The `Storage` interface focuses on upload/download/store/read and bucket lifecycle. To list objects by prefix, delimiter, fields, and pagination, use `ObjectStorageClient`:

~~~java
import com.oracle.bmc.objectstorage.requests.ListObjectsRequest;
import com.oracle.cloud.spring.storage.Storage;

var client = storage.getClient();
String namespace = storage.getNamespaceName();

var response = client.listObjects(
        ListObjectsRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucketName)
                .prefix("contracts/tenant-001/")
                .limit(1000)
                .build());

var objects = response.getListObjects().getObjects();
~~~

`ListObjects` returns up to 1,000 objects per response. By default it returns only object names; if you need size, ETag, `timeCreated`, `timeModified`, or `storageTier`, specify `fields` per the API reference.

### 9.2. Handling Next Pages

~~~java
String start = null;

do {
    var requestBuilder = ListObjectsRequest.builder()
            .namespaceName(namespace)
            .bucketName(bucketName)
            .prefix(prefix)
            .limit(1000);

    if (start != null) {
        requestBuilder.start(start);
    }

    var page = client.listObjects(requestBuilder.build())
            .getListObjects();

    page.getObjects().forEach(object -> {
        processSummary(object.getName(), object.getSize(), object.getEtag());
    });

    start = page.getNextStartWith();
} while (start != null);
~~~

Pass `nextStartWith` from the response as `start` for the next request. Do not increment numeric offsets by object count, because the API uses an object-name marker. For large lists, process page by page instead of collecting all object names onto the heap.

### 9.3. Prefix and Delimiter

`prefix` filters object keys starting with the specified string. A delimiter `/` can group remaining segments into common prefixes to simulate folders. This does not mean OCI creates physical directories.

Use tenant-scoped or document-type-scoped prefixes to avoid listing the entire bucket. IAM policies can restrict `target.object.name` by pattern when required.

## 10. Metadata, ETag, and Versioning

### 10.1. System Metadata and Custom Metadata

System metadata includes `Content-Type`, `Content-Length`, `ETag`, `Last-Modified`, `Cache-Control`, `Content-Disposition`, and storage info. Custom metadata is sent as key/value pairs with the `opc-meta` prefix in request headers.

Metadata can be used to:

- Record document type or non-sensitive business codes.
- Set `Content-Disposition` for downloads.
- Set appropriate `Cache-Control`.
- Attach correlation/reference IDs.
- Store application-computed checksums if required.

Metadata should not replace a database. Do not use custom metadata as the primary source of truth for business state, ownership, or authorization.

### 10.2. ETag and Conditional Requests

An ETag represents a content version per service semantics. You can use `If-Match` to update only if the object still has the previously read ETag, or `If-None-Match` with `*` to create an object only if it does not yet exist.

Example creating without overwriting:

~~~java
StorageObjectMetadata metadata =
        StorageObjectMetadata.builder()
                .contentType("application/pdf")
                .ifNoneMatch("*")
                .build();

storage.upload(bucketName, objectKey, inputStream, metadata);
~~~

If two requests attempt to create the same key simultaneously, one can succeed while the other receives a precondition/conflict failure. The application must return a clear business error or generate a different object key.

### 10.3. Object Versioning

Buckets can enable versioning to preserve object versions upon overwrites/deletes. The `Storage` API supports:

~~~java
Resource olderVersion =
        storage.download(bucketName, objectKey, versionId);
~~~

Versioning protects against accidental changes but increases object/version counts and storage costs. Combine it with lifecycle/retention policies to manage noncurrent versions. Do not assume deleting an object key permanently deletes every version when bucket versioning is enabled.

### 10.4. Strong Consistency and Concurrency

Strong consistency ensures reads see the latest record after a successful write. ETags/conditional requests are still necessary when multiple writers update the same object. For data requiring multi-object transactions, store business state in a database and use Object Storage for blobs; Object Storage does not provide multi-object ACID transactions.

## 11. Large File Uploads and Multipart Uploads

### 11.1. When to Use Multipart?

OCI recommends multipart uploads for objects larger than 100 MiB. Multipart splits a file into parts, uploads each part, and then commits them into a single object.

Key limits:

- Maximum single object size: 10 TiB.
- Maximum single part size: 50 GiB.
- Part numbers from 1 to 10,000.
- Parts can be uploaded in parallel or in any order.
- On commit, Object Storage assembles parts by part number.
- If one part fails, only that part needs to be re-uploaded rather than resending the entire file.

### 11.2. Using `UploadManager`

The OCI Java SDK provides `UploadManager`, which automatically chooses `PutObject` or multipart based on `UploadConfiguration`. It can split files into parts, upload in parallel, and retry individual parts.

Default `UploadConfiguration` enables multipart and parallel uploads; the default threshold for switching to multipart is 128 MiB, the default part size is 128 MiB, and the limit is 10,000 parts. Thresholds/part sizes can be tuned for bandwidth, memory, concurrent uploads, and timeouts, but do not raise them across the board without load measurements.

~~~java
import com.oracle.bmc.objectstorage.model.PutObjectRequest;
import com.oracle.bmc.objectstorage.transfer.UploadConfiguration;
import com.oracle.bmc.objectstorage.transfer.UploadManager;
import java.io.File;

File file = new File("/data/contracts/large-contract.pdf");

PutObjectRequest putRequest = PutObjectRequest.builder()
        .namespaceName(storage.getNamespaceName())
        .bucketName(bucketName)
        .objectName(objectKey)
        .contentType("application/pdf")
        .build();

UploadConfiguration configuration =
        UploadConfiguration.builder()
                .allowMultipartUploads(true)
                .allowParallelUploads(true)
                .build();

UploadManager uploadManager =
        new UploadManager(storage.getClient(), configuration);

UploadManager.UploadRequest uploadRequest =
        UploadManager.UploadRequest.builder(file)
                .allowOverwrite(false)
                .build(putRequest);

UploadManager.UploadResponse response =
        uploadManager.upload(uploadRequest);
~~~

`UploadRequest.builder(file)` reads the size from `File` and can re-read the file for multipart/parallel processing. If using an `InputStream`, you must supply the content length; for effective parallel uploads, the stream source must support re-reading/duplication per SDK guidance.

`allowOverwrite(false)` prevents overwriting an existing object using `If-None-Match`. When intentional replacement is needed, enable overwrite and control concurrency via ETag/version or a new object key.

### 11.3. Multipart and IAM Permissions

Multipart requires more permissions than a simple `PUT`. OCI requires `OBJECT_CREATE` and `OBJECT_OVERWRITE` for `CreateMultipartUpload`/`UploadPart`; `CommitMultipartUpload` may also require `BUCKET_READ`, `OBJECT_CREATE`, `OBJECT_READ`, and `OBJECT_OVERWRITE` per the permission mapping.

A policy granting only `OBJECT_CREATE` can allow small uploads to succeed while multipart uploads fail. Check the permission matrix and test files exceeding the multipart threshold in a test environment.

### 11.4. Cleaning Up Incomplete Uploads

If a process crashes or an upload is canceled, uncommitted multipart uploads may remain. By default, `UploadManager` attempts to abort the multipart upload on failure. If managing raw multipart APIs manually, implement `AbortMultipartUpload` and appropriate lifecycle cleanup/monitoring.

Do not let incomplete uploads linger indefinitely, because uploaded parts can incur storage costs.

### 11.5. Spring Boot Resource Limits

- Limit multipart request size at the reverse proxy and in Spring.
- Do not hold large files in `byte[]`.
- Use temporary disk/quarantine storage when scanning is needed.
- Bound concurrent uploads and parallel-part executors.
- Set reasonable timeouts that accommodate slower networks.
- Verify checksums before/after upload if integrity is required.
- Use unique object keys so two uploads do not write the same object.
- Never let clients control part sizes or unbounded thread counts.

## 12. Pre-Authenticated Requests (PAR)

### 12.1. What Is a PAR Used For?

A PAR generates a pre-authorized URL allowing recipients to read/write a bucket or object without OCI sign-in credentials. It is a bearer URL: anyone possessing the URL can exercise the granted permissions and scope.

Use cases:

- A partner downloading a contract.
- A browser uploading a file directly to a specific object.
- Users receiving reports without needing OCI accounts.

Do not use PARs for internal service-to-service access. Workload-to-workload traffic should use IAM principals and SDK authentication.

### 12.2. Limiting PAR Scope

A PAR can be created for:

- A specific object.
- Objects matching a prefix.
- All objects in a bucket.

The access type can be read, write, or read/write. Object listing is denied by default; enable it only when the use case requires it. A PAR never permits recipients to delete buckets or objects.

Expiration is mandatory, though OCI sets no universal maximum cap on expiration duration. Therefore the application should enforce short TTLs per use case and manage expiration dates.

### 12.3. Creating a PAR with the OCI SDK

The `Storage` bean provides `ObjectStorageClient` via `getClient()`. Example creating a read-only PAR for a single object:

~~~java
import com.oracle.bmc.objectstorage.model.CreatePreauthenticatedRequestDetails;
import com.oracle.bmc.objectstorage.requests.CreatePreauthenticatedRequestRequest;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public String createDownloadPar(
        String bucketName,
        String objectName,
        String region) {

    var details = CreatePreauthenticatedRequestDetails.builder()
            .name("document-download")
            .objectName(objectName)
            .accessType(
                    CreatePreauthenticatedRequestDetails.AccessType.ObjectRead)
            .timeExpires(Date.from(
                    Instant.now().plus(Duration.ofMinutes(15))))
            .build();

    var request = CreatePreauthenticatedRequestRequest.builder()
            .namespaceName(storage.getNamespaceName())
            .bucketName(bucketName)
            .createPreauthenticatedRequestDetails(details)
            .build();

    var par = storage.getClient()
            .createPreauthenticatedRequest(request)
            .getPreauthenticatedRequest();

    return "https://objectstorage." + region
            + ".oraclecloud.com" + par.getAccessUri();
}
~~~

This illustrates a download PAR. For uploads, use access type `ObjectWrite` and grant appropriate permissions. PAR names should not contain sensitive data. The access URI is returned only at creation time; OCI does not store the full URL for later retrieval. Store the URL immediately in a properly protected location if the business needs to re-issue it to the recipient.

### 12.4. Permissions to Create a PAR

The principal creating a PAR needs `PAR_MANAGE` on the bucket. In addition, the principal must hold the permissions corresponding to the granted access type:

- Read: `OBJECT_READ`.
- Upload: `OBJECT_CREATE` and `OBJECT_OVERWRITE`.
- Read/write: `OBJECT_READ`, `OBJECT_CREATE`, and `OBJECT_OVERWRITE`.

If the creator is deleted or loses the required permissions, the PAR also stops working. OCI checks the creator's permissions every time the PAR is used.

### 12.5. Revoking and Protecting PARs

- Delete a PAR using `DeletePreauthenticatedRequest` to revoke access.
- Set short expiry times.
- Scope to a single specific object whenever possible.
- Do not enable bucket listing unless necessary.
- Deliver the URL over a verified recipient channel.
- Do not log the URL, query/path token, or send it to analytics.
- Do not store PAR URLs unencrypted in databases/logs.
- Do not leak PARs via browser referrers or third-party analytics.
- Audit creator, target, access type, expiry, and revocation time.

A PAR URL is a bearer credential. If leaked, anyone can use it until expiration or until the PAR is deleted / the creator's permissions are revoked.

## 13. IAM Policies for `document-service`

### 13.1. Read-Only Policy

If the workload only reads objects in the contracts bucket:

~~~text
Allow dynamic-group DocumentService to read objects in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  target.object.name = 'contracts/*'
}
~~~

If the service needs to list objects, it needs `inspect objects`. If it needs to list buckets, it may need `BUCKET_INSPECT` or a matching policy. `GetNamespace` requires no special permission when retrieving the caller's own namespace.

### 13.2. Policy for Uploads

Example where a service only creates new objects in an inbox bucket and lists needed objects:

~~~text
Allow dynamic-group DocumentService to read buckets in compartment AppData
where target.bucket.name = 'contract-inbox'

Allow dynamic-group DocumentService to manage objects in compartment AppData
where all {
  target.bucket.name = 'contract-inbox',
  any {
    request.permission = 'OBJECT_CREATE',
    request.permission = 'OBJECT_INSPECT'
  }
}
~~~

The policy condition restricts `manage objects` to `OBJECT_CREATE` and `OBJECT_INSPECT`. If the service needs to overwrite existing objects, add `OBJECT_OVERWRITE`. If using multipart uploads, include both `OBJECT_CREATE` and `OBJECT_OVERWRITE` along with required commit operation permissions.

### 13.3. Policy for Uploads and Downloads in One Setup

~~~text
Allow dynamic-group DocumentService to read buckets in compartment AppData
where target.bucket.name = 'contracts-prod'

Allow dynamic-group DocumentService to read objects in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  target.object.name = 'contracts/*'
}

Allow dynamic-group DocumentService to manage objects in compartment AppData
where all {
  target.bucket.name = 'contract-inbox',
  any {
    request.permission = 'OBJECT_CREATE',
    request.permission = 'OBJECT_OVERWRITE',
    request.permission = 'OBJECT_INSPECT'
  }
}
~~~

Separating a read-only bucket from an upload inbox narrows blast radius. If the service uploads once with unique object keys, prefer create-only and unique keys to prevent overwrites.

### 13.4. Policy for PARs

The principal creating a PAR needs `PAR_MANAGE` on the bucket plus object permissions matching the access type. For example, a contract-sharing group that only creates read PARs for objects under the `contracts` prefix:

~~~text
Allow dynamic-group DocumentShareService to manage buckets in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  request.permission = 'PAR_MANAGE'
}

Allow dynamic-group DocumentShareService to read objects in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  target.object.name = 'contracts/*'
}
~~~

If creating upload PARs, add a statement granting `OBJECT_CREATE` and `OBJECT_OVERWRITE` on the target bucket/objects. Do not grant `manage object-family` or tenancy-wide access when only creating PARs for a single bucket.

### 13.5. KMS Customer-Managed Keys

If a bucket uses a customer-managed key, IAM also needs key-association permissions and the Object Storage service principal needs encrypt/decrypt permissions under KMS policies. For buckets encrypted with a KMS key, `PutObject` may require `KEY_ENCRYPT`; `GetObject` may require `KEY_DECRYPT` for the Object Storage service principal. Grant the right key compartment and key policy per OCI guidelines.

### 13.6. Policies Do Not Replace Business Authorization

IAM policies permit the workload to access a bucket. They do not know whether the end user is authorized to download a specific document ID. Spring Boot must still verify tenant, owner, classification, and business permissions before calling the `Storage` API or creating a PAR.

## 14. Data and Network Security

### 14.1. Private Buckets

Keep buckets private unless public access has been formally evaluated and approved. Use OCI IAM policies for internal workloads and PARs for controlled sharing. Never make a bucket public to resolve a 403 error.

### 14.2. Encryption at Rest

OCI Object Storage encrypts data at rest. You can use default Oracle-managed keys or customer-managed keys when key control is required. For customer-managed keys:

- Choose a Vault/Key in the matching region.
- Grant `KEY_ASSOCIATE` for attaching the key.
- Grant `KEY_ENCRYPT`/`KEY_DECRYPT`/`KEY_READ` to the Object Storage service principal as required.
- Test upload/download after modifying key policies.
- Never disable or destroy keys still protecting objects, versions, or backups.

### 14.3. TLS and Private Connectivity

Use HTTPS for all requests. For workloads in private subnets, use a Service Gateway to reach Object Storage over the OCI network backbone without requiring NAT/public internet egress for that path.

A Service Gateway does not replace IAM policies. Network reachability and authorization are two separate layers.

### 14.4. Protecting Object Names and Metadata

Do not put PII or secrets in object keys, because keys can appear in audit/access logs. Metadata should likewise avoid sensitive content. Use opaque IDs, classification labels, and pseudonymized references.

### 14.5. Upload Controls

Before moving an object into the primary storage area:

- Verify tenant and upload permissions.
- Enforce size and file count limits.
- Validate actual file extension and MIME type.
- Run malware scanning if required.
- Verify checksums.
- Generate the object key on the server.
- Stage files into a quarantine prefix/bucket prior to scanning.
- Prevent uploads from overwriting already-approved objects.
- Record audit events with actor, document ID, object key reference, and outcome.

## 15. Retries, Errors, and Correctness

### 15.1. Strong Consistency Does Not Eliminate Retries

OCI Object Storage provides strong consistency, yet a request can still time out after the server finishes processing it. If the client resends `PUT`, it might create/overwrite the object again. Use unique object keys, `If-None-Match`, or `If-Match` to make semantics explicit.

### 15.2. SDK Retries

The OCI Java SDK provides retry configuration for supported operations. Transient errors such as timeouts, connection errors, 429s, or certain 5xx responses can be retried according to SDK policy. Do not assume every operation is automatically retried, and do not retry indefinitely.

For uploads:

- Use re-readable files/streams for retries or multipart uploads.
- Use unique object keys or conditional requests.
- Check object existence after a timeout before resending.
- Do not retry 401/403 errors as network errors.
- When managing multipart manually, track upload IDs and abort incomplete uploads.

SDK asynchronous clients differ in retry support; check documentation for your exact version before switching from sync to async.

### 15.3. Common Errors

| Error | Possible Cause | Resolution |
| --- | --- | --- |
| `401 NotAuthenticated` | Wrong auth profile, key, token, or workload identity | Verify config type, credentials, and runtime |
| `403 NotAuthorizedOrNotFound` | Missing IAM permission, wrong compartment, or bucket scope | Check principal, policy, target bucket, and object |
| `404 object not found` | Wrong namespace, bucket, object key, or version | Verify exact key and region |
| `409 conflict` | Bucket/object already exists or invalid state | Use unique keys, conditional requests, and check state |
| `412 precondition failed` | ETag/`If-None-Match` no longer satisfied | Re-read metadata and handle concurrency |
| `429 Too Many Requests` | Rate limits or burst traffic | Backoff with jitter, limit concurrency |
| `5xx`/timeout | Transient network/service issue | Bounded retry and log request ID |
| Multipart upload 403 | Missing `OBJECT_CREATE`/`OBJECT_OVERWRITE` or `BUCKET_READ` | Check multipart permission matrix |
| Resource opens via plain HTTP | Starter resolver not registered | Check starter dependency and URI format |
| `WritableResource` upload incomplete | `OutputStream` not closed | Use `try-with-resources` |
| File download causes heap OOM | `readAllBytes` or buffering full file | Stream via `InputStream`/`StreamingResponseBody` |
| Object overwritten | Shared object key or missing condition | Use UUID keys/`If-None-Match`/`If-Match` |
| PAR URL rejected | Expired, deleted, creator lost permissions, or truncated URL | Check PAR metadata, creator policy, and full URL |
| `UploadManager` multipart fails | Missing policy permission, non-repeatable stream, or part error | Use `File`/repeatable stream, check policy, and abort |
| Cannot list objects | Missing `OBJECT_INSPECT` | Grant inspect on target bucket/prefix |

### 15.4. Recording Request IDs

OCI SDK responses include `opc-request-id`. Log the request ID alongside timestamp, service, region, operation, and object reference for investigation. Never log `Authorization` headers, PAR URLs, object contents, or secrets.

### 15.5. ETags and Checksums

ETags are useful for conditional requests and detecting object modifications. Do not assume an ETag is always the MD5 of the entire object, especially for multipart uploads. If the business needs a durable checksum, compute SHA-256 in the application and store it in controlled database/metadata records.

## 16. Observability and Operations

### 16.1. Metrics

Monitor:

- Upload/download/delete counts by bucket and service.
- Total bytes uploaded/downloaded.
- Upload duration and download latency.
- Error rates by status/service code.
- In-flight/incomplete multipart upload counts.
- PARs created, expired, and revoked.
- Requests denied by IAM.
- Storage usage, object count, and storage tier.
- Connection/thread pool wait times.

Never put object names containing PII or PAR URLs into metric labels.

### 16.2. Auditing

Enable Cloud Audit Logs/Data Access or Object Storage logging as needed. Record application-level audit events in Spring Boot to link the end user to the business document ID. Cloud audit logs capture OCI principals, API operations, and resources, but do not automatically understand business intent.

### 16.3. Lifecycle and Version Retention

Buckets can configure lifecycle rules to transition storage tiers or delete expired objects/versions. Versioning keeps older versions but increases costs. Design retention, legal holds, lifecycle rules, and backups according to data classification.

### 16.4. Disaster Recovery

Object Storage is a regional service that stores data redundantly within a region. If cross-region DR is required, design replication policies and verify destination buckets/regions. IAM policies, KMS keys, lifecycle rules, and PARs are not automatically replicated the same way objects are; verify each component.

### 16.5. Cost Awareness

Costs are not just GB stored:

- API requests and list calls.
- Data retrieval by storage tier.
- Cross-region replication/transfer.
- Uncommitted multipart parts.
- Old versions and backups.
- Logging/monitoring.
- Unused, unrevoked PARs do not directly incur URL charges, yet increase security risk.

Avoid listing an entire bucket on every request. Use prefixes, pagination, metadata caching, and database indexes to locate objects.

## 17. Integration Testing

### 17.1. Unit Testing the Storage Service

Mock the `Storage` interface and verify:

- Uploads use the right bucket/key.
- Metadata includes content type/length.
- Object keys are generated server-side.
- Downloads request the right object.
- Deletes are called only after authorization.
- Exceptions are mapped into appropriate business errors.
- Streams or file contents are never logged.

### 17.2. Spring `Resource` Tests

With an integration test against an OCI test environment:

- `ResourceLoader` resolves the URL to `OracleStorageResource`.
- `Resource.isReadable()` returns true.
- `getInputStream()` reads the exact bytes.
- `WritableResource.getOutputStream()` writes the object upon closing.
- Re-reading the object succeeds after upload.
- Object keys with prefixes and special characters are encoded properly.
- There is no fallback to unauthenticated `UrlResource`.

### 17.3. OCI Integration Tests

Use a dedicated test tenancy, compartment, bucket, and workload identity. Generate a unique object key per test and clean up afterward.

Test:

1. Uploading a new object.
2. Downloading and comparing checksums.
3. Listing by prefix and reading paginated results.
4. Verifying metadata/ETag.
5. Uploading with `If-None-Match` to verify no overwrite occurs.
6. Uploading a large file via `UploadManager`.
7. Creating a PAR for an object and testing `GET`/`PUT` per access type.
8. Deleting the PAR and confirming the URL is rejected.
9. Attempting to access an out-of-scope bucket and confirming 403.
10. Checking request IDs and audit events.

Never run destructive tests against production buckets. Use dedicated prefixes, temporary buckets, and least-privilege policies.

### 17.4. Testing IAM Negative Cases

Testing denied permissions is just as important as testing allowed ones:

- Principal can read `contracts-prod` but cannot read other buckets.
- Principal can upload to `contract-inbox` but cannot delete objects.
- Principal cannot create buckets or modify IAM policies.
- Users in tenant A cannot download documents belonging to tenant B.
- PAR only reads the specified object and cannot list the bucket.
- Object keys under other prefixes are denied.

### 17.5. Testing Retries and Concurrency

- Given two concurrent requests with the same object key and `If-None-Match`, only one succeeds.
- Updating with a stale ETag is rejected.
- A timeout after upload does not create unintended duplicate objects.
- A failed multipart part can be retried and ultimately commits the complete object.
- Client disconnects close the stream and release resources.
- Concurrent downloads do not share an unsafe `InputStream`.

## 18. Comprehensive Practice Exercise

You are tasked with building `document-service` on OCI. The service stores PDF contracts in the `contracts-prod` bucket, stores metadata in PostgreSQL, and exposes REST APIs for authenticated users. An external partner outside OCI needs to upload packages into `contract-inbox` and download approved files via a time-limited URL.

**Tasks:**

1. Create `contracts-prod` and `contract-inbox` buckets in compartment `AppData` via IaC or Console.
2. Configure the Spring Cloud Oracle 2.0.4 storage starter.
3. Use a `FILE` profile locally and Instance Principal/OKE Workload Identity in production.
4. Configure `region.static` and `compartment.static` for each environment.
5. Implement a `Storage` service to upload PDFs with content type, content length, and custom metadata.
6. Implement a download endpoint using `StreamingResponseBody`.
7. Resolve OCI object URLs into `Resource` and `WritableResource`.
8. Generate object keys server-side from tenant/document IDs.
9. Implement `ListObjects` pagination by prefix.
10. Use `UploadManager` for files exceeding the multipart threshold.
11. Configure IAM policies allowing read-only access on `contracts-prod` and uploads to `contract-inbox`.
12. Create an `ObjectRead` PAR for partners with a 15-minute TTL and revoke it upon completion.
13. Write unit/integration tests covering upload/download/list/PAR/denied access.
14. Record audit events for upload, download, export, and revocation.
15. Write a runbook for handling 401/403/404/412, timeouts, and incomplete multipart uploads.

**Self-Assessment Questions:**

- How does a namespace differ from a bucket and a compartment?
- Why doesn't an object key containing slashes create physical directories?
- Does Object Storage strong consistency eliminate the need for ETags?
- Which bean does the Spring Cloud Oracle starter provide?
- How do `Resource` and `WritableResource` differ?
- Why isn't an Object Storage URI automatically a public URL?
- When do you use the `Storage` API vs. the OCI Java SDK directly?
- Why shouldn't you call `getFile()` on an Object Storage `Resource`?
- What problem does `UploadManager` solve for large files?
- Which permissions does a multipart upload require?
- Why is `If-None-Match` helpful during uploads?
- Is an ETag always the MD5 hash of the object?
- Why is a PAR a bearer URL, and how can it be revoked?
- Why must a PAR URL be saved immediately upon creation?
- Why must the workload still check end-user permissions before calling `Storage`?
- Why should a service stream files instead of calling `readAllBytes`?
- Why should you test IAM negative/denied cases?
- Why should versioning and lifecycle rules be designed together?

**Guided Answers:** Namespace is a tenancy-level top-level container; bucket is a regional container inside a compartment; object keys are flat names that may use prefixes; strong consistency does not prevent concurrent overwrites; the starter registers a `Storage` bean and protocol resolver; `Resource` reads while `WritableResource` writes; URL `Resource` routes through OCI SDK/auth when the starter's resolver is registered; `Storage` API handles common CRUD while the SDK handles listing/PARs/multipart; a remote resource is not a local file; `UploadManager` splits parts and retries individual parts; multipart requires `OBJECT_CREATE` and `OBJECT_OVERWRITE` plus commit permissions; `If-None-Match` prevents overwrites; ETags are not universal MD5 checksums; PARs are revoked with `DeletePreauthenticatedRequest` and expire per `timeExpires`; the URL appears only on creation so it must be stored securely; business authorization belongs in Spring Boot; streaming reduces heap usage; negative tests prove least privilege; versioning preserves old versions while lifecycle governs retention/deletion.

## 19. Official References

### Spring Cloud Oracle and Spring Framework

- [Spring Cloud Oracle 2.0.4 – OCI Object Storage](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/storage/): `Storage` bean, upload, `Resource`, and `WritableResource`.
- [Spring Cloud Oracle – OCI Core](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/): authentication types, region, and compartment properties.
- [Spring Cloud Oracle – Configuration Properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/): auth, region, compartment, and `storage.enabled` configuration.
- [Spring Cloud Oracle 2.0.4 – Storage Javadocs](https://oracle.github.io/spring-cloud-oracle/2.0.4/javadocs/com/oracle/cloud/spring/storage/Storage.html): `Storage` methods, upload/download, read/store, and `getClient`.
- [Spring Cloud Oracle 2.0.4 – StorageObjectMetadata](https://oracle.github.io/spring-cloud-oracle/2.0.4/javadocs/com/oracle/cloud/spring/storage/StorageObjectMetadata.html): content metadata, conditional requests, and encryption fields.
- [Spring Framework – Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ResourceLoader`, `WritableResource`, and stream contracts.
- [Spring Cloud Oracle – Release Notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/): Spring Boot/Spring Framework compatibility and `WritableResource` changes.

### OCI Object Storage

- [Overview of Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm): buckets, objects, namespaces, compartments, regional service, and strong consistency.
- [Object Storage Namespaces](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/understandingnamespaces.htm): tenancy namespaces and how to retrieve them.
- [Object Storage Objects](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm): object naming, metadata, and conditional requests.
- [Object Storage Multipart Uploads](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingmultipartuploads.htm): multipart workflow, part limits, and required IAM permissions.
- [OCI Java SDK – UploadManager](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/transfer/UploadManager.html): upload manager automatically choosing single PUT or multipart.
- [OCI Java SDK – ListObjects](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/ObjectStorage.html): listing, fields, and pagination.
- [Object Storage Pre-Authenticated Requests](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests.htm): PAR scope, permissions, expiry, and revocation.
- [Create Pre-Authenticated Request](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests_topic-To_create_a_preauthenticated_request_for_all_objects_in_a_bucket.htm): creating PARs for buckets/objects/prefixes.
- [Delete Pre-Authenticated Request](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests_topic-To_delete_a_preauthenticated_request.htm): revoking PARs.
- [Object Storage Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm): resource types and permissions for buckets/objects/PAR/multipart and KMS.
- [OCI Common Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm): sample Object Storage read/write policies and bucket/object conditions.
- [Object Storage Security](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm): least privilege, public buckets, and IAM conditions.
- [OCI Java SDK Concepts](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm): client reuse, retries, large objects, and SDK threading model.

**Key Takeaways:** The `Storage` API is convenient for object CRUD; Spring `Resource` integrates objects into Spring streaming APIs; the OCI Java SDK handles specialized features like pagination, multipart uploads, and PARs. Configure proper identities and IAM policies, keep buckets private, generate object keys server-side, use conditional writes when needed, and stream data instead of loading entire files into memory.

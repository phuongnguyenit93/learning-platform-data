# Integrating Cloud Storage with the Client and Spring Resource

## 1. Context and Objectives

A Spring Boot application often needs to read or write documents, images, reports, export files, and other binary content. On Google Cloud, **Cloud Storage** provides the object storage API; the Java client library provides the `Storage` object to interact directly with buckets and objects. Spring Framework adds the **`Resource`** abstraction so applications can read many types of data sources through a unified interface, such as local files, classpath resources, URLs, and objects in Cloud Storage.

**Spring Framework on Google Cloud** (formerly commonly called Spring Cloud GCP) integrates these two approaches. The Storage starter auto-configures a `Storage` bean and supports resource URIs of the form `gs://bucket/object`. As a result, a service can use the Cloud Storage API when specialized operations are needed, or use Spring `Resource`/`WritableResource` when passing content through Spring APIs that already accept Resource.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on the Cloud Storage client and the Spring Resource abstraction.

After this lesson, you will be able to:

- Add the proper BOM and Storage starter to a Spring Boot application.
- Understand `Storage`, `Blob`, `BlobInfo`, `BlobId`, and the role of the Google Cloud Storage Java client.
- Configure Application Default Credentials (ADC), project ID, and IAM for local/production environments.
- Inject a GCS object with `@Value("gs://...") Resource` or retrieve it dynamically via `ResourceLoader`.
- Read using `Resource`, write via `WritableResource`, and manipulate metadata through `GoogleStorageResource`.
- Choose between Spring Resource and the Storage API based on streaming, generation, precondition, and metadata requirements.
- Control automatic bucket/object creation, stream closing, error handling, and integration testing.

> **Version scope:** Examples use the Java Cloud Storage client and Spring Framework on Google Cloud. Package names, starters, properties, and auto-configuration capabilities depend on the release. Use the Spring Framework on Google Cloud BOM to lock versions consistently and check the Spring Boot/Spring Cloud/JDK compatibility matrix for your chosen release. Do not mix examples from older Spring Cloud GCP generations with the current release without checking the migration guide.

## 2. Two Integration Layers: Storage Client and Spring Resource

There are two main approaches when an application works with objects:

1. **Cloud Storage Java client:** uses `Storage` and classes such as `Blob`, `BlobInfo`, and `BlobId` to work directly with buckets/objects. This is suitable when you need generations, metadata, preconditions, listing, streaming, and GCS-specific features.
2. **Spring Resource abstraction:** represents an object as a `Resource` or `WritableResource` with the URI `gs://bucket/object`. This is useful when a Spring component already accepts `Resource` as input/output and does not need to depend directly on GCS APIs.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> CHOICE{"Access approach"}
    CHOICE --> CLIENT["Cloud Storage Java client"]
    CHOICE --> RESOURCE["Spring Resource abstraction"]
    CLIENT --> STORAGE["Storage bean"]
    RESOURCE --> RES["Resource / WritableResource<br/>gs://bucket/object"]
    RES --> STORAGE
    STORAGE --> GCS["Google Cloud Storage"]
    IAM["ADC / workload identity"] -. "Provides credentials" .-> STORAGE
~~~

| Criterion | `Storage` client | `Resource` / `WritableResource` |
| --- | --- | --- |
| Primary API | `Storage`, `Blob`, `BlobInfo`, `BlobId` | `Resource`, `InputStreamSource`, `WritableResource` |
| Identifier | Bucket + object name + optional generation per API | URI `gs://bucket/object` |
| Reading content | `Storage.reader(...)`, `Blob`, or download APIs | `getInputStream()` |
| Writing content | `Storage.create(...)`, `Storage.writer(...)` | `getOutputStream()` |
| Metadata | Direct access to `Blob`/`BlobInfo` | Can cast to `GoogleStorageResource` to access `Blob` |
| Preconditions/version | Controlled directly via API options | Must use Storage API when detailed conditions are needed |
| Spring dependency | Optional | Required; needs Spring Framework on Google Cloud resource integration |
| Best-fit scenarios | Storage adapters, large uploads, versioning, metadata, IAM-sensitive operations | Spring APIs accepting Resource, reading templates, config, simple file import/export |

The two approaches are not mutually exclusive. An application can use `Resource` for simple file-reading flows and use the `Storage` client for uploads requiring preconditions, metadata, or generation handling. Both still rely on the same project, credentials, IAM, and bucket.

## 3. Preparing Dependencies and Versions

### 3.1. Using the Spring Framework on Google Cloud BOM

The BOM manages versions for Spring Framework on Google Cloud modules and related dependencies. Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-gcp.version` is a project-managed property. Choose a release available in Maven Central that is compatible with your Spring Boot/Spring Cloud versions. Compatibility documentation for the current 7.x release specifies Spring Boot 3.5.x and Spring Cloud 2025.0.x; older releases have different matrices. Do not upgrade the starter on its own while omitting the BOM.

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation(
        platform("com.google.cloud:spring-cloud-gcp-dependencies:$springCloudGcpVersion")
    )
    implementation("com.google.cloud:spring-cloud-gcp-starter-storage")
}
~~~

The Storage starter pulls in the required modules and integrates with the core starter. If your application source code directly imports Google Cloud Storage Java client classes and dependency policy requires direct declaration, add `com.google.cloud:google-cloud-storage` managed by the same BOM; avoid pinning a different version from the one managed by the starter.

### 3.2. Distinguishing the Starter and the Java Client

| Component | Responsibility |
| --- | --- |
| `spring-cloud-gcp-starter` | Core Google Cloud configuration such as project ID and credentials provider |
| `spring-cloud-gcp-starter-storage` | Integrates Cloud Storage and Spring Resource; auto-configures the Storage bean |
| `google-cloud-storage` | Java client API for operating on buckets and objects |
| Spring `Resource` | Resource-reading abstraction |
| Spring `WritableResource` | Opens a writable stream for resources |

If the application only uses the plain `Storage` client, the Java client library alone may suffice. When `gs://` Resource integration and Spring auto-configuration are needed, use the appropriate Storage starter.

### 3.3. Checking the Dependency Graph

When encountering `NoSuchMethodError`, `ClassNotFoundException`, or missing beans, check:

- Spring Boot, the Spring Cloud release train, and the Spring Framework on Google Cloud BOM.
- Resolved versions of `google-cloud-storage`, `google-auth-library`, and Google API modules.
- Whether an older library transitively pulls in a different Spring Cloud GCP version.
- Whether the Storage starter is on the runtime classpath, not just the compile classpath.
- Whether any configuration disables auto-configuration or excludes dependencies.

Do not resolve a mismatch by adding an arbitrary version to a dependency. Identify which module pulls in the conflicting version and fix dependency management.

## 4. How Spring Framework on Google Cloud Configures Storage

When the Storage starter is on the classpath and auto-configuration is enabled, Spring Framework on Google Cloud creates a `Storage` bean in the ApplicationContext. This bean uses the core starter's credentials provider and project configuration.

~~~java
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class DocumentCatalog {

    private final Storage storage;

    public DocumentCatalog(Storage storage) {
        this.storage = storage;
    }
}
~~~

The application does not need to manually call `StorageOptions.getDefaultInstance().getService()` in every service. Injecting the configured bean lets adapters share project/credentials settings and simplifies testing.

If custom client settings are required, you can define your own `Storage` bean, but you must check auto-configuration conditions to avoid two competing beans or accidentally losing default credentials configuration. Never instantiate a new `Storage` client per HTTP request.

### 4.1. Project ID

The Project ID can be provided explicitly:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: training-platform-dev
~~~

If the property is not set, the starter can discover the project from environment sources such as `GOOGLE_CLOUD_PROJECT`, credentials project metadata, Google Cloud SDK, or runtime metadata depending on precedence/version. In CI and deployment environments, configure the project ID explicitly to avoid running against the wrong project.

**A Project ID is not a bucket name.** One project can have multiple buckets, and a bucket name does not fully encode project/location/permissions.

## 5. Authentication: Application Default Credentials and IAM

### 5.1. What Is ADC?

**Application Default Credentials (ADC)** is the mechanism Google Cloud client libraries use to locate credentials based on the environment. The Java client and Spring Framework on Google Cloud can use ADC without the source code knowing how credentials were provisioned.

Common environments:

| Environment | Recommended identity source |
| --- | --- |
| Developer laptop | ADC created by `gcloud auth application-default login` per organization policy |
| External CI outside Google Cloud | Workload Identity Federation or an appropriate OIDC mechanism |
| Cloud Run | Service account attached to the service |
| GKE | Workload Identity Federation for GKE |
| Compute Engine | Service account attached to the VM |

Distinguish between the two commands:

- `gcloud auth login`: logs in to use the Google Cloud CLI with a user account.
- `gcloud auth application-default login`: sets up ADC for applications running locally.

Logging into the CLI successfully does not automatically guarantee that the Java process has valid ADC. Verify the exact user, credential source, project, and permissions of the principal the application is using.

### 5.2. Do Not Put Service Account Keys in Source Code

Prefer workload identity or ADC rather than downloading a service account JSON key and packaging it into an image. A service account key is a long-lived credential; if leaked, others can use it outside the deployment lifecycle.

Properties like `spring.cloud.gcp.credentials.location` or `spring.cloud.gcp.credentials.encoded-key` exist for cases requiring custom credential configuration, but should not be the default choice on Google Cloud runtimes. If an organization requires a key, manage it through a secret store, restrict IAM, protect the file, and maintain a rotation/revocation process.

### 5.3. Least-Privilege IAM for Cloud Storage

Common predefined roles:

| IAM role | General permissions | Use case |
| --- | --- | --- |
| `roles/storage.objectViewer` | Read objects and metadata | Service that only downloads documents |
| `roles/storage.objectCreator` | Create new objects; does not implicitly allow reading, deleting, or overwriting existing objects | Service that only uploads new objects |
| `roles/storage.objectUser` | Broader object operations such as create, read, update, and delete per role definition | Service managing object lifecycle |
| `roles/storage.objectAdmin` | Administer objects within the granted scope | Object operations tools |
| `roles/storage.admin` | Broad administration of buckets and objects | Infrastructure administration teams, not default for runtime |

Assign roles at bucket scope when only one bucket is needed; avoid granting `roles/storage.admin` at project scope to an upload-only application. With multiple tenants, a prefix in the object name does not automatically create an IAM boundary. Design resource separation, appropriate IAM conditions, or adapter-level authorization.

### 5.4. Local and Production Configuration

Example configuration without keys:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: ${GOOGLE_CLOUD_PROJECT}

app:
  storage:
    bucket: ${APP_DOCUMENT_BUCKET}
~~~

Local development can use developer ADC; production uses the service account/workload identity attached to the workload. Do not put JSON private keys into committed YAML files.

## 6. Using the Cloud Storage Java Client Directly

### 6.1. Core Classes

| Class | Role |
| --- | --- |
| `Storage` | Client/service interface for Cloud Storage operations |
| `BlobId` | Identifies bucket, object name, and optionally generation |
| `BlobInfo` | Describes an object when creating/updating, including content type and metadata |
| `Blob` | Object along with its available metadata |
| `Bucket` | Bucket information |
| `ReadChannel` | Reads an object as a channel, suitable for streaming/seeking |
| `WriteChannel` | Writes an object as a channel |

`Storage` is a synchronous Java client. If called inside a Spring MVC controller, the call blocks the thread until the operation completes. Do not call blocking storage APIs directly on the Spring WebFlux event loop; if using a reactive pipeline, isolate blocking I/O onto a suitable scheduler or choose a compatible client/adapter design.

### 6.2. Creating a New Object

Example uploading small content:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class GcsDocumentClient {

    private final Storage storage;

    public GcsDocumentClient(Storage storage) {
        this.storage = storage;
    }

    public long createText(
            String bucket,
            String objectName,
            String content) {

        BlobInfo info = BlobInfo.newBuilder(
                        BlobId.of(bucket, objectName))
                .setContentType("text/plain; charset=utf-8")
                .setMetadata(Map.of(
                        "source-system", "document-api",
                        "classification", "internal"))
                .build();

        Blob created = storage.create(
                info,
                content.getBytes(StandardCharsets.UTF_8),
                Storage.BlobTargetOption.doesNotExist());

        return created.getGeneration();
    }
}
~~~

`doesNotExist()` is a precondition: create the object only if no live object with that name exists. If the object already exists, the operation fails instead of silently overwriting. This avoids race conditions between an existence check and an upload.

The `byte[]` example is suitable for small payloads. Do not read a multi-hundred-MB file into heap just to pass it to `storage.create(...)`; use streaming or resumable uploads for large files.

### 6.3. Reading Objects and Metadata

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public class GcsObjectReader {

    private final Storage storage;

    public GcsObjectReader(Storage storage) {
        this.storage = storage;
    }

    public Blob describe(String bucket, String objectName) {
        Blob blob = storage.get(BlobId.of(bucket, objectName));
        if (blob == null) {
            throw new IllegalArgumentException("Object does not exist");
        }
        return blob;
    }
}
~~~

`storage.get(...)` reads object metadata; `Blob` can provide content type, size, generation, metageneration, custom metadata, and other attributes. Reading byte content is a separate stream; do not confuse fetching metadata with downloading the entire object.

### 6.4. Streaming Content Reads

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.Channels;

public byte[] downloadSmallObject(
        Storage storage,
        String bucket,
        String objectName) throws IOException {

    BlobId id = BlobId.of(bucket, objectName);

    try (ReadChannel channel = storage.reader(id);
         InputStream input = Channels.newInputStream(channel);
         ByteArrayOutputStream output = new ByteArrayOutputStream()) {

        input.transferTo(output);
        return output.toByteArray();
    }
}
~~~

The method name emphasizes `SmallObject`: the example buffers all bytes into memory for simplicity. For large objects, stream `InputStream` directly to a file or HTTP response with size limits, rather than using an unbounded `ByteArrayOutputStream`.

### 6.5. Writing Large Files via WriteChannel

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.Channels;
import java.io.OutputStream;

public void uploadStream(
        Storage storage,
        BlobInfo info,
        InputStream source) throws IOException {

    try (WriteChannel channel = storage.writer(info);
         OutputStream output = Channels.newOutputStream(channel)) {
        source.transferTo(output);
    }
}
~~~

`WriteChannel` streams data instead of holding the entire object in heap. In production, review chunk size configuration, retries, resumable upload settings, checksums, and whether the source stream is replayable. Close the channel/output stream properly to finalize the upload and release resources.

### 6.6. Updating Metadata

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.util.Map;

public Blob updateClassification(
        Storage storage,
        String bucket,
        String objectName,
        String classification) {

    Blob current = storage.get(
            com.google.cloud.storage.BlobId.of(bucket, objectName));

    if (current == null) {
        throw new IllegalArgumentException("Object does not exist");
    }

    Map<String, String> metadata = current.getMetadata() == null
            ? new java.util.HashMap<>()
            : new java.util.HashMap<>(current.getMetadata());

    metadata.put("classification", classification);

    BlobInfo updatedInfo = current.toBuilder()
            .setMetadata(metadata)
            .build();

    return storage.update(
            updatedInfo,
            Storage.BlobTargetOption.metagenerationMatch(
                    current.getMetageneration()));
}
~~~

The example reads the current metadata, merges the key, and updates with `metagenerationMatch`. If another worker changes the metadata after the read, the precondition fails; the application must re-read and merge instead of overwriting unconditionally. In real code, translate precondition failures into controlled conflict/retry handling.

## 7. Spring Resource Abstraction for GCS

### 7.1. What Is Resource?

Spring `Resource` is an abstraction representing a data source. Common implementations include:

- `ClassPathResource`: file on the classpath.
- `FileSystemResource`: file on the filesystem.
- `UrlResource`: resource accessed via URL.
- `ByteArrayResource`: content backed by a byte array.
- `GoogleStorageResource`: Cloud Storage object or bucket via `gs://`.

`Resource` provides common operations such as `getInputStream()`, `exists()`, `isReadable()`, `contentLength()`, and `getFilename()`. `WritableResource` extends `Resource` with `getOutputStream()` for writing data.

**A GCS object is not a local file.** Do not assume `getFile()` returns a `java.io.File` or `Path` that can be passed to `Files.*`. Use streams; inspection methods such as `exists()` and `contentLength()` can trigger network requests and require IAM permissions.

### 7.2. URI gs://bucket/object

Spring Framework on Google Cloud supports the `gs://` protocol to represent objects:

~~~text
gs://training-documents-dev/reports/2026/summary.pdf
~~~

When the Storage starter is configured, the resource resolver recognizes the `gs` scheme and creates a `GoogleStorageResource`. This URI is a Cloud Storage identifier, not a public download URL.

`GoogleStorageResource` implements Spring `WritableResource` and can represent a bucket or a blob. When the URI points to an object, you can access `Blob` to read metadata or call specialized GCS APIs.

### 7.3. Injecting a Resource with @Value

Example configuration:

~~~yaml
app:
  gcs:
    bucket: training-documents-dev
    object: reports/2026/summary.pdf
~~~

Injecting the resource:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class ReportResource {

    private final Resource resource;

    public ReportResource(
            @Value("gs://${app.gcs.bucket}/${app.gcs.object}")
            Resource resource) {
        this.resource = resource;
    }

    public Resource getResource() {
        return resource;
    }
}
~~~

Spring resolves property placeholders first, then uses the resource protocol resolver for the `gs` scheme. This fits well when the bucket/object is a static configuration for a bean. If paths vary per request/tenant, do not create a `@Value` bean for each object; use `ResourceLoader` or the Storage client with validated inputs.

### 7.4. Resolving Resources Dynamically via ApplicationContext

You can use `ResourceLoader`/`ApplicationContext` when the object name is determined at runtime:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class DynamicGcsResourceFactory {

    private final ApplicationContext applicationContext;

    public DynamicGcsResourceFactory(
            ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public Resource get(String bucket, String objectName) {
        validate(bucket, objectName);
        String location = "gs://" + bucket + "/" + objectName;
        return applicationContext.getResource(location);
    }

    private void validate(String bucket, String objectName) {
        if (bucket == null || bucket.isBlank()
                || objectName == null || objectName.isBlank()) {
            throw new IllegalArgumentException("Invalid bucket/object name");
        }
        if (objectName.startsWith("/") || objectName.contains("../")) {
            throw new IllegalArgumentException("Invalid object name");
        }
    }
}
~~~

This validation example is only a basic step and does not replace full naming rules and authorization. Do not concatenate URIs directly from untrusted input and allow arbitrary bucket access. The application must constrain buckets/prefixes by tenant and business permissions.

### 7.5. Reading Content via Resource

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class GcsResourceReader {

    public byte[] readSmall(Resource resource) throws IOException {
        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalStateException("Resource is not readable");
        }

        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

The example uses `readAllBytes()` for small documents. For large objects, stream to the consumer and enforce size limits. `exists()`/`isReadable()` may execute Cloud Storage queries; avoid calling them repeatedly within a single request if you already have metadata results.

### 7.6. Writing Content via WritableResource

~~~java
import java.io.IOException;
import java.io.OutputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.WritableResource;
import org.springframework.stereotype.Service;

@Service
public class GcsResourceWriter {

    public void write(Resource resource, byte[] content) throws IOException {
        if (!(resource instanceof WritableResource writable)) {
            throw new IllegalArgumentException(
                    "Resource is not writable");
        }

        try (OutputStream output = writable.getOutputStream()) {
            output.write(content);
        }
    }
}
~~~

Not every `Resource` is writable; always check `WritableResource`. Close `OutputStream` properly to complete the write operation. Verify auto-create, overwrite, and metadata behavior for the Spring Framework on Google Cloud version in use.

## 8. GoogleStorageResource: When You Need GCS APIs from a Resource

If you need more specialized operations from a resource URI, you can cast to `GoogleStorageResource`:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.spring.storage.GoogleStorageResource;
import org.springframework.core.io.Resource;

public Blob getBlobMetadata(Resource resource) {
    if (!(resource instanceof GoogleStorageResource gcsResource)) {
        throw new IllegalArgumentException(
                "Resource is not a GoogleStorageResource");
    }

    Blob blob = gcsResource.getBlob();
    if (blob == null) {
        throw new IllegalStateException("Object does not exist");
    }
    return blob;
}
~~~

`GoogleStorageResource` belongs to package `com.google.cloud.spring.storage`. Check APIs and constructors against your project's BOM version; do not instantiate objects using constructors from a different release.

### 8.1. Reading Metadata

`getBlob()` returns object details if the resource points to an existing blob. You can retrieve:

- Content type.
- Size.
- Generation and metageneration.
- Custom metadata.
- Storage class and timestamps per the API.

Do not call `getBlob()` on a resource representing only a bucket and assume it is an object. Distinguish bucket URIs from object URIs.

### 8.2. Updating Content Type

Example using the `GoogleStorageResource` API:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.spring.storage.GoogleStorageResource;
import org.springframework.core.io.Resource;

public void setContentType(Resource resource, String contentType) {
    if (!(resource instanceof GoogleStorageResource gcsResource)) {
        throw new IllegalArgumentException("Resource is not a GCS resource");
    }

    Blob current = gcsResource.getBlob();
    if (current == null) {
        throw new IllegalStateException("Object does not exist");
    }

    current.toBuilder()
            .setContentType(contentType)
            .build()
            .update();
}
~~~

This operation updates metadata on the real object. If multiple workers can update metadata concurrently, use the Storage API with a metageneration precondition to protect updates; do not assume every Resource helper method enforces the business conditions you need.

### 8.3. getURI and getURL

With `GoogleStorageResource`, `getURI()` represents the address using the `gs://` scheme. `getURL()` may return the self-link URL of the bucket/blob depending on the library version; the two values should not be treated as equivalent.

If a business API needs a GCS identifier, use bucket + object name or the `gs://` URI. If a browser needs a URL, design a dedicated access mechanism such as a signed URL; do not send a selfLink or `gs://` URI to users as if it were a public download link.

### 8.4. Signed URLs

`GoogleStorageResource` can support generating signed URLs under appropriate conditions. Creating a signed URL requires a signing-capable credential (typically a service account credential or supported signing mechanism). User-token ADC or workload identity does not always have a local private key for direct signing.

A signed URL is a time-limited bearer token: anyone holding the URL can execute the signed operation during its validity period. Do not log URLs in public logs, do not set overly long expirations, and do not let clients request signing for arbitrary objects outside their authorization scope.

## 9. Controlling Automatic Bucket and Object Creation

Spring Framework on Google Cloud Storage provides the `spring.cloud.gcp.storage.auto-create-files` property. According to release documentation, this property controls automatic creation of files/objects and buckets when writing to a non-existent resource; the documented default value in current configurations is `true`.

Explicit configuration example:

~~~yaml
spring:
  cloud:
    gcp:
      storage:
        enabled: true
        auto-create-files: false
~~~

When auto-create is disabled, the application must provision buckets/objects through infrastructure workflows and ensure the bucket exists before writing. This is usually easier to govern in production because bucket creation affects location, storage class, UBLA, public access prevention, retention, lifecycle, and billing.

If auto-create is kept enabled for local/dev, control IAM permissions and isolate resource naming. Do not grant broad bucket administration permissions to runtime workloads just so the starter can auto-create buckets in production.

## 10. Choosing Resource or the Storage API?

### 10.1. When Spring Resource Fits

Use `Resource` when:

- A Spring API accepts `Resource`, `InputStreamSource`, or `WritableResource`.
- You want to inject a `gs://...` URI via `@Value`.
- Reading templates, configuration files, small contents, or input data from GCS.
- You want a simple adapter sharing an interface with file/classpath resources.
- You do not need deep control over generation, metadata concurrency, or specialized operations.

For example, a service can accept `Resource` from multiple sources without knowing GCS details:

~~~java
public String loadTemplate(Resource template) throws IOException {
    try (var reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(
                    template.getInputStream(),
                    java.nio.charset.StandardCharsets.UTF_8))) {
        return reader.lines()
                .collect(java.util.stream.Collectors.joining("\n"));
    }
}
~~~

### 10.2. When the Storage Client Fits

Use the `Storage` client when you need:

- Large file uploads/downloads via `ReadChannel`/`WriteChannel`.
- Generation/metageneration preconditions.
- Object versioning and reading specific generations.
- Controlled custom metadata updates.
- Listing objects by prefix/delimiter.
- Bucket lifecycle, IAM-related metadata, or bucket operations.
- Signed URLs, rewrite/copy, compose, or specialized GCS features.
- Control over retries, checksums, and request options.

### 10.3. Guidelines for Combining Both

| Requirement | Preferred approach | Reason |
| --- | --- | --- |
| Read a fixed template | `Resource` | Concise code, Spring-compatible |
| Write small content to a known object | `WritableResource` or `Storage` | Choose based on precondition/metadata needs |
| Upload large files | `Storage.writer`/streaming API | Better stream and resource control |
| Create an object only if it does not exist | `Storage` with precondition | Prevents race conditions |
| Update metadata concurrently | `Storage` with metageneration precondition | Resource helpers do not express full conditions |
| List objects by prefix | `Storage.list(...)` | Direct API with pagination |
| Integrate with Spring APIs accepting Resource | `Resource` | Uses unified abstraction |

Do not force every operation through Resource just because the starter is present. An abstraction is helpful when it simplifies code; when specific GCS semantics are needed, use the client API directly.

## 11. IAM, Bucket Policy, and Production Configuration

### 11.1. Workload Permissions

The application needs a service account or workload identity with appropriate IAM roles on the bucket/project. For example:

- Document-reading service: `roles/storage.objectViewer`.
- New-object upload service: `roles/storage.objectCreator`.
- Service needing read and update/delete on objects: consider `roles/storage.objectUser` or a properly scoped custom role.
- Bucket administration tools: appropriate admin roles, separated from runtime services.

Permission to read objects does not imply permission to list or create buckets. Check the actual operations executed by the code and grant least-privilege permissions. When `Resource.exists()` or `contentLength()` calls metadata APIs, the principal needs the corresponding metadata read permissions.

### 11.2. Do Not Rely on Object Names for Tenant Isolation

If all tenants reside in the same bucket, a prefix such as `tenant-a/` is only an object naming convention. If the service account has permission to read the entire bucket, code passing only the prefix `tenant-a/` is not a security boundary. Enforce authorization in the application, use appropriate IAM conditions, or separate buckets/projects when strong isolation is required.

### 11.3. UBLA and Public Access Prevention

For new buckets, consider Uniform bucket-level access (UBLA) to manage permissions via IAM instead of object/bucket ACLs. Public Access Prevention helps block unintended public access grants. These are distinct settings and can be used together per organization policy.

Do not make a bucket public to resolve file download errors. If users need to download content, issue time-limited signed URLs after backend business authorization checks.

### 11.4. Do Not Put Secrets in Metadata or Log URLs

Do not store passwords, access tokens, session tokens, or sensitive personal data in custom metadata. Metadata can be read by any principal allowed to view the object. Signed URLs should also be treated as secrets during their validity window.

## 12. Integration Testing

### 12.1. Unit Tests

Unit tests focus on business logic and adapters:

- Validate bucket/object names.
- Map document IDs to object names.
- Select content type and metadata.
- Handle object not found.
- Handle permission/precondition errors.
- Ensure streams are always closed on errors.

Mock `Storage` or build a fake adapter so real Google Cloud calls are not needed in unit tests.

### 12.2. Integration Tests on a Dedicated Project

The Cloud Storage Java client requires integration tests against a dedicated test project/bucket to verify real semantics:

1. Use a test service account or workload identity with least-privilege permissions.
2. Create the bucket through a separate provisioning workflow, avoiding uncontrolled runtime bucket auto-creation.
3. Read and write objects via the `Storage` client.
4. Read objects via Spring `Resource` using a `gs://...` URI.
5. Write via `WritableResource` and verify content using the Storage client.
6. Update metadata and verify generation/metageneration.
7. Test missing permissions and non-existent objects.
8. Clean up objects/buckets per test procedures; do not delete shared buckets.

### 12.3. Fake Servers/Emulators

You can use a third-party fake GCS server or emulator to test certain request/object APIs locally. However, clearly verify the emulator's supported features and limitations. Do not assume features such as IAM, signed URLs, retention, HNS, soft delete, lifecycle, or generation preconditions are emulated identically to production.

For critical properties, run a small integration test on a GCP test project to verify real service behavior. Do not use a production project for tests that create generations, modify metadata, or delete objects.

### 12.4. Testing Spring Resource

An integration test can verify both abstractions:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class GcsResourceIntegrationTest {

    @Autowired
    ResourceLoader resourceLoader;

    @Test
    void shouldReadObjectThroughSpringResource() throws Exception {
        Resource resource = resourceLoader.getResource(
                "gs://training-documents-test/fixtures/hello.txt");

        try (InputStream input = resource.getInputStream()) {
            String content = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

            assertEquals("hello from gcs", content);
        }
    }
}
~~~

The example assumes the fixture bucket/object already exists and the Spring Storage starter has registered the protocol resolver. Tests must run with valid test ADC/IAM; do not place production service account keys in test fixtures.

### 12.5. Verifying Differences Between Resource and Storage

Tests should verify:

- `Resource.exists()` for existing and non-existent objects.
- `Resource.getInputStream()` reads the expected bytes.
- `WritableResource.getOutputStream()` writes the object properly.
- Storage client reads back content type and metadata.
- Objects are created only when the appropriate precondition holds.
- Permission denied is mapped to a clear application error.

Do not check only `resource != null`: creating a `gs://...` handle does not prove the object exists or that the principal has access permission.

## 13. Common Errors and Troubleshooting

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Unable to resolve `gs://...` | Missing Storage starter or protocol resolver not registered | Check dependencies, auto-configuration, and ApplicationContext |
| `NoSuchBeanDefinitionException` for `Storage` | Starter missing, excluded, or disabled by config | Check `spring-cloud-gcp-starter-storage`, properties, and BOM |
| `403 Forbidden` | ADC principal lacks IAM permissions or blocked by bucket policy | Verify principal, project/bucket scope, and role |
| `401 Unauthorized` | Invalid ADC/token or expired credentials | Check ADC source and runtime identity |
| `Resource` created but `exists()` is false | Syntactically valid URI, but object does not exist or wrong bucket/key | Cross-check bucket/object name and project |
| `getFile()` throws exception | GCS Resource is not a local file | Use `getInputStream()`/`getOutputStream()` |
| Writing object accidentally creates bucket | `auto-create-files` is enabled and resource did not exist | Disable auto-create when explicit provisioning is needed |
| Metadata not updated as expected | Partial metadata update or missing precondition | Read Blob, merge metadata, and use metageneration condition |
| Java uses different ADC than gcloud CLI | Logged into gcloud user account without creating ADC or different workload identity | Check ADC source and the Java process principal |
| Large upload increases heap usage | Reading entire object into `byte[]` | Switch to channel/streaming/resumable upload |
| Local test passes but real GCP fails | Emulator does not simulate IAM or service semantics | Run smoke tests on a GCP test project |

### 13.1. Diagnosing in Order

1. **Dependencies:** Are the Storage starter and Google Cloud client versions resolved properly?
2. **Auto-configuration:** Are the `Storage` bean and `gs://` protocol resolver registered?
3. **Project:** Which project is the application targeting?
4. **Credentials:** Which ADC/service account/workload identity is the Java process using?
5. **IAM:** Does the principal have the right permissions on the bucket/object?
6. **Resource path:** Are the bucket and object name accurate?
7. **Lifecycle:** Are the bucket/object provisioned; is auto-create enabled?
8. **Streams:** Are InputStream/OutputStream closed, and is the data size appropriate?
9. **Concurrency:** Do generation/metageneration preconditions match the current version?

Do not resolve 403 errors by immediately granting `roles/storage.admin`. Find the specific permission required by the operation.

## 14. Designing a Testable Spring Boot Adapter

Controllers and domain services should depend on a business interface instead of `Blob`, `Storage`, or `GoogleStorageResource`:

~~~java
import java.io.InputStream;

public interface DocumentStorage {
    StoredDocument upload(
            String documentId,
            InputStream content,
            String contentType);

    InputStream open(String documentId);
}

public record StoredDocument(
        String bucket,
        String objectName,
        long generation,
        String contentType,
        long size) {}
~~~

A GCS adapter implements the interface using the `Storage` client; another adapter can use `ResourceLoader` if the use case mainly reads resources. Unit tests can use a fake `DocumentStorage`, while integration tests verify the GCS adapter against a test bucket.

Interface design should accurately model the business domain. If the application needs version tokens, preconditions, metadata, or signed URLs, include those concepts intentionally in the contract instead of hiding important semantics behind an overly generic interface.

## 15. Comprehensive Hands-On Exercise

**Context:** A Spring Boot application manages training documents. Template documents are stored in bucket `training-documents-dev` with object name `lessons/spring-cloud/intro.md`. One service needs to read the template when creating a course; another service uploads a PDF export when requested by a user.

### Task A — Configure the Client

1. Add the `spring-cloud-gcp-dependencies` BOM and `spring-cloud-gcp-starter-storage`.
2. Explain why the starter can auto-create the `Storage` bean.
3. Configure project ID and bucket via environment variables/properties.
4. Set up ADC locally and workload identity for deployed environments.
5. State the least-privilege IAM roles for the template-reading service and the PDF-uploading service.

### Task B — Use Spring Resource

1. Inject `gs://training-documents-dev/lessons/spring-cloud/intro.md` using `@Value`.
2. Read the content via `getInputStream()` and close the stream.
3. Use `ResourceLoader` when the object name is determined per request.
4. Write via `WritableResource` and explain when casting is required.
5. Explain why `getFile()` is unsuitable for Cloud Storage objects.

### Task C — Use the Storage API

1. Build `BlobInfo` with content type `application/pdf` and custom metadata.
2. Upload the object only if it does not exist using `doesNotExist()`.
3. Read generation and metadata after uploading.
4. Update metadata using a metageneration precondition.
5. Choose `WriteChannel` for large files and describe how to close the stream.

### Task D — Testing

- Unit test the service with a fake `DocumentStorage`.
- Integration test the `Storage` bean and `gs://` Resource against a test bucket.
- Test IAM permission denied.
- Test `auto-create-files` enabled/disabled.
- Test non-existent object and generation conflict.
- Compare emulator results with smoke tests on a GCP test project.

**Pass criteria:** Learners know when to use `Storage` versus Spring Resource; configure starter/ADC/IAM properly; read/write streams safely; handle metadata/preconditions; and test both bean auto-configuration and real objects.

## 16. Comparison with AWS S3 and Azure Blob Storage

| Requirement | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Java service client | `Storage` from `google-cloud-storage` | `S3Client` from AWS SDK v2 | `BlobServiceClient`/`BlobContainerClient` from Azure SDK |
| Spring resource abstraction | `GoogleStorageResource` via `gs://` | Does not share the same GCS `gs://` Resource by default; usually a custom adapter | Can build a `Resource` adapter on top of the Azure Blob client |
| Credentials | ADC, service account, Workload Identity | IAM role, AWS SDK credential provider chain | Managed Identity, Entra ID credential chain |
| Resource identifier | `gs://bucket/object` | Bucket + object key / S3 URI | Storage account + container + blob name |
| Version/concurrency | Generation, metageneration, preconditions | Version ID, ETag, and conditional requests | Version ID, ETag, lease, and conditional headers |
| Integration testing | GCP test project/bucket or limited emulators | AWS sandbox, LocalStack | Azure test account or Azurite for Storage |

Commonalities include needing a client SDK, identity, least-privilege permissions, and streaming. Differences lie in resource representation, version tokens, conditional operations, and Spring integration. Do not assume a GCS `Resource` implementation works with S3/Azure; if a multi-cloud abstraction is needed, build a business interface with dedicated per-provider adapters.

## 17. Key Takeaways

- **`Storage` client** is the direct API for managing buckets/objects; **`Resource`** is Spring's abstraction for reading data sources; **`WritableResource`** adds write capability.
- Spring Framework on Google Cloud Storage starter auto-configures the `Storage` bean and supports `gs://bucket/object` resource URIs.
- `@Value("gs://...") Resource` fits statically configured resources; `ResourceLoader` fits paths determined at runtime.
- `GoogleStorageResource` gives access to `Blob` and specialized GCS APIs; use the Storage client directly when generation, preconditions, metadata, or advanced streaming are required.
- ADC and workload identity avoid storing long-lived service account keys in source code or images.
- Do not assume a GCS Resource is a local file; use streams and close them properly.
- Control `auto-create-files`, IAM, and project/bucket configuration to prevent unintended resource creation.
- Combine unit tests, integration tests, and smoke tests on a dedicated project to verify both Spring wiring and real GCP permissions.

### References

- [Spring Framework on Google Cloud — Cloud Storage](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/#cloud-storage)
- [GoogleStorageResource API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/GoogleStorageResource.html)
- [Google Cloud Storage Java client](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)

# Mapping Cloud Resources to Spring Resource

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications integrate managed services from AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries, SDKs, and drivers. Many applications need to read resources from the classpath, file system, HTTP endpoints, Amazon S3, Google Cloud Storage, or Azure Blob Storage.

Spring Framework provides the **`Resource`** abstraction to describe a readable resource without forcing the calling code to know where the data resides. **`ResourceLoader`** resolves a location string into a `Resource`. As a result, services can read via `getInputStream()` instead of handling each storage type manually.

Object storage is not a file system. An object on S3 does not necessarily have a local path, cannot be converted to `java.io.File` by default, and a read operation may involve network calls, IAM permission checks, request costs, or opening a stream that must be closed properly. Spring Resource is a resource access abstraction; it does not automatically turn every cloud URI into a scheme supported by Spring.

This lesson uses Amazon S3 as an example to build an `s3://bucket/key` adapter via the `ProtocolResolver` extension point. Similar principles apply to Google Cloud Storage and Azure Blob Storage, though URI schemes, SDKs, identities, metadata, and semantics must be defined individually for each provider.

After this lesson, you will be able to:

1. Distinguish between `Resource`, `ResourceLoader`, and `ResourcePatternResolver`.
2. Understand `Resource` methods and limitations when a resource resides in the cloud.
3. Map cloud URIs such as `s3://bucket/key` to a Spring Resource implementation.
4. Register `ProtocolResolver` and use `DefaultResourceLoader` in Spring Boot.
5. Read objects via streaming, and manage streams, metadata, errors, and request costs.
6. Design secure access permissions, tenant boundaries, URI validation, and credential providers.
7. Distinguish read abstractions from upload/write, caching, and wildcard listing.
8. Test the adapter with unit tests, mock SDKs, LocalStack, and cloud staging.

> **Scope:** `Resource` is well suited for representing readable resources. Upload, multipart, copy, delete, versioning, encryption, and conditional write should use storage APIs/ports with clear semantics. Do not assume that every cloud provider or Spring Cloud starter registers the same URI scheme.

## 2. Spring Resource Abstraction

### 2.1. What is `Resource`?

`org.springframework.core.io.Resource` is an interface describing a readable resource. It extends `InputStreamSource` and provides information such as whether the resource exists, is readable, its filename, description, URL/URI, or file-like accessibility.

Common implementations:

| Implementation | Resource Source | Example |
| --- | --- | --- |
| `ClassPathResource` | Application classpath | `classpath:templates/email.html` |
| `FileSystemResource` | File system | `file:/var/app/import/data.csv` |
| `UrlResource` | URL such as HTTP/HTTPS | `https://example.org/config.json` |
| `ByteArrayResource` | Byte array in memory | Small content generated at runtime |
| `InputStreamResource` | Existing InputStream | Stream provided by another API |
| `ServletContextResource` | Web application context | Resources in the servlet context |
| Custom Cloud Resource | Object storage/provider API | `s3://rental-documents/invoices/2026/01.pdf` |

The common denominator is that consuming code can use `getInputStream()`. However, other methods may have different capabilities: `FileSystemResource` can return a `File`, whereas an S3 resource has no local file.

### 2.2. Methods to Understand

| Method | Meaning | Notes for Cloud Resources |
| --- | --- | --- |
| `exists()` | Checks whether the resource exists | Typically requires a metadata/HEAD API call over the network |
| `isReadable()` | Whether the resource is readable according to the implementation | May require read permissions; does not guarantee subsequent reads will succeed |
| `isOpen()` | Whether the resource represents an already-open stream | Resource handles typically return false; InputStreamResource may return true |
| `isFile()` | Whether the resource is represented as a file | Object storage typically returns false |
| `getInputStream()` | Opens a stream to read the content | Each call should open a new stream if supported by the implementation; the caller must close it |
| `contentLength()` | Content length | May invoke a HEAD/metadata API; avoid calling repeatedly |
| `lastModified()` | Last modified timestamp | Depends on provider metadata |
| `getFilename()` | Filename/last segment of the path | For an object key, typically the final segment after the slash |
| `getURL()` / `getURI()` | URL/URI identifying the resource | A cloud URI is not necessarily a directly accessible HTTP URL |
| `getFile()` | Returns a local file | Cannot be used with object storage unless downloaded first |
| `createRelative()` | Creates a relative resource | Object key path rules differ from file system rules |

Do not call `getFile()` as a universal way to read any Resource. Portable code should use `getInputStream()` and close the stream with try-with-resources.

### 2.3. Resource Is a Handle, Not Downloaded Content

Example of reading a small resource:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public String readText(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

For large objects, `readAllBytes()` keeps the entire content in the heap and can cause an `OutOfMemoryError`. Process it as a stream instead:

~~~java
try (InputStream input = resource.getInputStream()) {
    Files.copy(input, destination, StandardCopyOption.REPLACE_EXISTING);
}
~~~

A `Resource` is not synonymous with an already-open stream. Call `getInputStream()` when you need to read, close the stream after processing, and do not share the same InputStream across multiple threads.

### 2.4. Methods That Can Trigger Network I/O

For a cloud resource, the following calls may send requests to the provider:

- `exists()` may perform a HEAD or metadata lookup.
- `contentLength()` may perform a HEAD request.
- `lastModified()` may perform a HEAD request.
- `getInputStream()` opens a connection to read the object.
- `isReadable()` may check metadata or permissions.

Do not call `exists()` followed by `getInputStream()` repeatedly in a loop if unnecessary. Two operations can generate two network requests and still suffer from a race condition: the object could be deleted or permissions changed between the check and the read. In many use cases, opening the stream once and handling not-found/forbidden errors from the read operation makes more sense.

Clearly distinguish between 404 and 403. A non-existent object may return 404 if the principal has the required permissions; when lacking bucket listing permissions, some APIs may withhold whether the object exists and return 403. Do not turn every authorization error into "resource does not exist".

## 3. ResourceLoader and Location Prefixes

### 3.1. ResourceLoader Resolves Locations

`org.springframework.core.io.ResourceLoader` provides the main method:

~~~java
Resource getResource(String location);
~~~

Common prefixes:

| Prefix | Meaning |
| --- | --- |
| `classpath:` | Look up resource in the classpath |
| `file:` | Resource from the file system |
| `http:` / `https:` | Resource from a URL |
| No prefix | Default rule depends on the ResourceLoader/ApplicationContext in use |

Examples:

~~~java
Resource classpathResource =
        resourceLoader.getResource("classpath:templates/report.html");

Resource localFile =
        resourceLoader.getResource("file:/var/app/import/report.csv");

Resource remoteUrl =
        resourceLoader.getResource("https://example.org/report.json");
~~~

`ResourceLoader` does not natively understand schemes such as `s3://`, `gs://`, or `azure-blob://`. These schemes only work when a starter/provider integration registers them or the application implements the corresponding resolver itself.

Do not assume that `@Value("s3://...") Resource` works automatically in every Spring Boot application. Resolution depends on the ApplicationContext and registered resolvers. With a custom resolver, you can create a dedicated `DefaultResourceLoader` and inject it explicitly into the components that need it.

### 3.2. ResourcePatternResolver vs. ResourceLoader

`ResourcePatternResolver` extends `ResourceLoader` and supports finding multiple resources by pattern, for example:

~~~java
Resource[] resources =
        resolver.getResources("classpath*:/migrations/*.sql");
~~~

The `classpath*:` pattern is useful for finding resources across multiple JAR/classpath locations. Do not infer that `s3://bucket/**/*.json` automatically lists every object in a bucket.

Cloud object listing requires dedicated provider APIs, pagination, permissions, and carries request costs. If you want to support patterns in the cloud, you must define clear semantics:

- Which list API are prefixes and wildcards translated into?
- Are there pagination and object count limits?
- Is the result ordering stable?
- Are versions/delete markers filtered?
- How much cost and latency can listing requests incur?
- How does the caller handle objects deleted during traversal?

A `ProtocolResolver` returning a single `Resource` does not automatically implement wildcard listing.
## 4. ProtocolResolver Extension Point

### 4.1. Why Do We Need a Resolver?

Spring provides the interface:

~~~java
public interface ProtocolResolver {
    Resource resolve(String location, ResourceLoader resourceLoader);
}
~~~

The resolver receives a location and returns a Resource if it recognizes the scheme; if it does not handle that location, it returns `null` so other resolvers can continue. `DefaultResourceLoader` allows registering resolvers via `addProtocolResolver`.

Example flow:

~~~mermaid
flowchart TD
    A["ResourceLoader.getResource(location)"] --> B["ProtocolResolver list"]
    B --> C{"Resolver recognizes scheme?"}
    C -->|Yes| D["Cloud Resource"]
    C -->|No| E["Default Spring resolution"]
    D --> F["Resource.getInputStream()"]
    F --> G["Cloud SDK / object storage"]
~~~

The resolver only parses the location and creates the resource handle. It should not download the entire object when `getResource()` is called. Content is only fetched when the caller invokes `getInputStream()`.

### 4.2. Registering a Resolver with DefaultResourceLoader

Example application-specific configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.DefaultResourceLoader;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class CloudResourceConfiguration {

    @Bean
    S3ProtocolResolver s3ProtocolResolver(S3Client s3Client) {
        return new S3ProtocolResolver(s3Client);
    }

    @Bean("cloudResourceLoader")
    DefaultResourceLoader cloudResourceLoader(
            S3ProtocolResolver s3ProtocolResolver) {
        DefaultResourceLoader loader = new DefaultResourceLoader();
        loader.addProtocolResolver(s3ProtocolResolver);
        return loader;
    }
}
~~~

This is a dedicated ResourceLoader bean named `cloudResourceLoader`. Inject it with `@Qualifier("cloudResourceLoader")` in components that need to read cloud resources. Do not claim this resolver automatically alters every `ApplicationContext.getResource()` call or every `@Value` in the application; context-wide behavior requires integrating into the ApplicationContext/resource loading strategy appropriate for the Spring version.

## 5. Designing URIs for Cloud Objects

### 5.1. URI Conventions

An easy-to-understand convention for S3:

~~~text
s3://<bucket>/<object-key>
~~~

Examples:

~~~text
s3://rental-documents/invoices/2026/INV-001.pdf
s3://rental-exports/tenant-a/2026/11/report.csv
~~~

The `s3://` scheme here is an application adapter convention. It is not a universal protocol understood automatically by every Spring application.

Other providers may use their own conventions:

| Provider | Example URI Convention | Notes |
| --- | --- | --- |
| AWS S3 | `s3://bucket/key` | Resolver uses S3 SDK/AWSpring integration |
| Google Cloud Storage | `gs://bucket/object` | Some Spring Cloud GCP integrations support Resource; check version and module |
| Azure Blob Storage | `azure-blob://account/container/blob` | May be an internal application-defined scheme; do not assume native Spring support |
| HTTP object gateway | `https://host/path` | Use UrlResource if the endpoint genuinely allows HTTP GET |

If an application needs multi-cloud support, you do not necessarily have to force every provider into the same URI string. You can define an internal locator type containing provider, container/bucket, object key, and version; then an adapter creates the corresponding Resource. A URI is only a serialization/lookup convention and should not become the sole domain identity if providers have differing semantics.

### 5.2. Parsing URIs with Validation

For S3, a URI needs a bucket and an object key:

- Scheme must be `s3`.
- Host must be a valid bucket.
- Path must contain the object key.
- Reject user info, port, query, or fragment if the adapter does not define those fields.
- Keys with special characters must be URI-encoded properly; do not arbitrarily replace plus signs or percent-encoding.
- Do not use end-user-supplied URIs directly without validating tenant, bucket allow-list, and permitted prefix.

Do not embed access keys, secrets, session tokens, or presigned URLs in configuration URIs. IAM credentials are supplied via the SDK credential provider chain.

## 6. AWS Example: S3 Resource via AWS SDK for Java 2.x

### 6.1. Dependencies

Use the AWS SDK BOM and S3 module:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>`aws.sdk.version`</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

If the AWSpring version in your project provides an S3 abstraction that satisfies the full use case, consider using that abstraction instead of rewriting all S3 operations. This example uses SDK v2 to illustrate the boundary between Resource and provider APIs; it is not a requirement for every project to build its own S3 adapter.

### 6.2. Creating a Shared S3Client

Declare the Region via environment configuration, without writing credentials into files:

~~~yaml
app:
  aws:
    region: ap-southeast-1
~~~

Minimal configuration record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.aws")
public record AwsIntegrationProperties(String region) {
}
~~~

Register the record using `@EnableConfigurationProperties(AwsIntegrationProperties.class)` or the application's configuration properties scanning.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
@EnableConfigurationProperties(AwsIntegrationProperties.class)
public class S3ClientConfiguration {

    @Bean(destroyMethod = "close")
    DefaultCredentialsProvider awsCredentialsProvider() {
        return DefaultCredentialsProvider.create();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(
            DefaultCredentialsProvider credentialsProvider,
            AwsIntegrationProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(credentialsProvider)
                .build();
    }
}
~~~

`S3Client` is thread-safe and should be shared as a Spring singleton bean. The AWS SDK uses the credential provider chain to obtain credentials based on the environment: ECS task role, EKS Pod Identity/IRSA, EC2 instance profile, or profiles for local development. Never place long-lived access keys in source code or Git-committed configuration files.

The Region must match the bucket and client configuration. For buckets across multiple Regions, an explicit client/Region strategy is needed; do not assume an arbitrary client Region will handle every bucket without proper configuration or redirect behavior.
### 6.3. Implementing S3ObjectResource

The implementation below focuses on reading objects and basic metadata:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Date;

import org.springframework.core.io.AbstractResource;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;

public final class S3ObjectResource extends AbstractResource {

    private final S3Client s3Client;
    private final String bucket;
    private final String key;

    public S3ObjectResource(S3Client s3Client, String bucket, String key) {
        this.s3Client = s3Client;
        this.bucket = bucket;
        this.key = key;
    }

    private HeadObjectResponse headObject() throws IOException {
        try {
            return s3Client.headObject(HeadObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());
        } catch (S3Exception ex) {
            if (ex.statusCode() == 404) {
                throw new FileNotFoundException(getDescription());
            }
            throw new IOException("Cannot read S3 object metadata: "
                    + getDescription(), ex);
        } catch (SdkClientException ex) {
            throw new IOException("S3 metadata request failed: "
                    + getDescription(), ex);
        }
    }

    @Override
    public boolean exists() {
        try {
            headObject();
            return true;
        } catch (FileNotFoundException ex) {
            return false;
        } catch (IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }
    }

    @Override
    public boolean isReadable() {
        return exists();
    }

    @Override
    public boolean isFile() {
        return false;
    }

    @Override
    public boolean isOpen() {
        return false;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        try {
            ResponseInputStream<?> stream = s3Client.getObject(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build());
            return stream;
        } catch (S3Exception ex) {
            if (ex.statusCode() == 404) {
                throw new FileNotFoundException(getDescription());
            }
            throw new IOException("Cannot open S3 object: "
                    + getDescription(), ex);
        } catch (SdkClientException ex) {
            throw new IOException("S3 object request failed: "
                    + getDescription(), ex);
        }
    }

    @Override
    public long contentLength() throws IOException {
        return headObject().contentLength();
    }

    @Override
    public long lastModified() throws IOException {
        Date modified = Date.from(headObject().lastModified());
        return modified.getTime();
    }

    @Override
    public String getFilename() {
        int slash = key.lastIndexOf('/');
        return slash >= 0 ? key.substring(slash + 1) : key;
    }

    @Override
    public java.io.File getFile() throws IOException {
        throw new FileNotFoundException(
                "S3 object is not a local file: " + getDescription());
    }

    @Override
    public String getDescription() {
        return "S3 object [s3://" + bucket + "/" + key + "]";
    }
}
~~~

Key points to understand:

- `getInputStream()` calls `GetObject` and returns the response stream. The caller must close the stream to release the HTTP connection.
- `exists()` and `isReadable()` use `HeadObject` to check metadata; this is a network call, not a free local check.
- `contentLength()` and `lastModified()` retrieve metadata from the HEAD response.
- `isFile()` returns false because the object is not a local file.
- `getFile()` throws a clear error instead of pretending the object has a local path.
- `getDescription()` uses the identifying URI, without containing access keys or presigned query strings.

This is a minimal implementation for demonstration. In production, consider retries, timeouts, provider error codes, object versions, SSE/KMS, request payer, checksums, environment-specific endpoints, and telemetry. Do not turn 403 into 404; permission failures must be preserved for diagnostics.

### 6.4. Limitations of the Sample Implementation

The implementation above makes deliberate choices:

1. `createRelative()` is not defined; do not assume object key path resolution matches a file system.
2. `getURL()` and `getURI()` do not return presigned URLs; the resource URI is strictly a locator.
3. `getFile()` does not download the object locally; if a file is needed, the caller must copy the stream to a temporary path with a clear lifecycle.
4. `exists()` may throw `UncheckedIOException` on network/permission errors other than not-found; callers must distinguish them.
5. `contentLength()`/`lastModified()` call HEAD every time; if optimization is needed, cache metadata with clear policies and invalidation.
6. The example assumes bucket/Region are validly configured and the client has `s3:GetObject` permission on the key.

Do not keep `ResponseInputStream` open in a field of the Resource. A Resource is an object descriptor; the stream is a resource with its own per-read lifecycle.
## 7. Registering S3 URIs via ProtocolResolver

### 7.1. S3ProtocolResolver

~~~java
import java.net.URI;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ProtocolResolver;
import org.springframework.core.io.ResourceLoader;

import software.amazon.awssdk.services.s3.S3Client;

public final class S3ProtocolResolver implements ProtocolResolver {

    private final S3Client s3Client;

    public S3ProtocolResolver(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    @Override
    public Resource resolve(String location, ResourceLoader resourceLoader) {
        if (!location.regionMatches(true, 0, "s3:", 0, 3)) {
            return null;
        }

        final URI uri;
        try {
            uri = URI.create(location);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid S3 resource URI", ex);
        }

        if (!"s3".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getPort() != -1
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException("Invalid S3 resource URI");
        }

        String path = uri.getPath();
        if (path == null || path.length() <= 1) {
            throw new IllegalArgumentException(
                    "S3 URI must include bucket and object key");
        }

        String key = path.substring(1);
        return new S3ObjectResource(s3Client, uri.getHost(), key);
    }
}
~~~

The resolver only handles the `s3` scheme; other schemes return `null`. If the location starts with `s3:` but the URI syntax is invalid, the resolver throws a clear error instead of letting Spring treat the string as a classpath path. The example rejects query/fragment/user info so the URI has a single unambiguous meaning.

If the application needs to support object versions, endpoint overrides, or encryption context, design separate locators/options and validate them explicitly rather than stuffing credentials into query strings. Object keys with special characters must be encoded/decoded consistently; test keys containing spaces, `%` signs, slashes, and Unicode.

### 7.2. Using ResourceLoader

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CloudDocumentReader {

    private final ResourceLoader resourceLoader;

    public CloudDocumentReader(
            @Qualifier("cloudResourceLoader") ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource resolve(String location) {
        return resourceLoader.getResource(location);
    }
}
~~~

Usage:

~~~java
Resource resource = cloudDocumentReader.resolve(
        "s3://rental-documents/invoices/2026/INV-001.pdf");

try (InputStream input = resource.getInputStream()) {
    // Stream to a parser or destination.
}
~~~

If a component only reads from S3, consider injecting a specific port such as `DocumentStorage` instead of allowing arbitrary location strings. A general-purpose ResourceLoader is more suitable when the use case genuinely needs to read multiple location types.

## 8. Mapping Resources Across AWS, Google Cloud, and Azure

### 8.1. Provider Differences to Preserve

| Aspect | AWS S3 | Google Cloud Storage | Azure Blob Storage |
| --- | --- | --- | --- |
| Common locator | Bucket + object key | Bucket + object name | Storage account + container + blob name |
| Java SDK | AWS SDK v2 S3 | Google Cloud Storage client | Azure Storage Blob SDK |
| Workload identity | IAM role / credential provider | Application Default Credentials / Workload Identity | Managed Identity / DefaultAzureCredential |
| Metadata | HeadObject, ETag, version ID, last modified | Blob metadata, generation, metageneration | Blob properties, ETag, version ID |
| Streaming read | GetObject response stream | ReadChannel/Blob read APIs | BlobInputStream |
| Conditional operations | ETag/version/condition headers | Generation preconditions | ETag conditions |
| URI scheme | Adapter can define `s3://` | Some Spring Cloud GCP modules have Resource integration with `gs://` | Scheme depends on integration or application convention |

A shared Resource abstraction can hide stream opening and some metadata. However, providers still differ in version/generation, ETag, encryption, retention, ACLs, consistency, retries, request costs, and conditional operations. When business logic requires those capabilities, do not strip them from the contract just to make every provider look identical.

### 8.2. Google Cloud Storage

Spring Cloud GCP provides integrations for Cloud Storage depending on the version; some releases offer a Resource loader for `gs://` locations. Before writing a custom resolver, check the exact starter/module and version in use to avoid registering duplicate schemes or overlooking built-in features.

If a custom adapter is needed, implement `ProtocolResolver` using the Google Cloud Storage client and a dedicated `Resource`. Corresponding metadata/read operations can use APIs to fetch Blob metadata and open a ReadChannel/stream. Authentication should use Application Default Credentials or Workload Identity; do not put service account keys into URIs or source code.

### 8.3. Azure Blob Storage

The Azure Storage Blob SDK provides `BlobServiceClient`, `BlobContainerClient`, and `BlobClient` for reading properties and opening streams. Azure Spring integrations may provide templates/operations depending on the version, but do not assume a universal ResourceLoader scheme across all applications.

If `azure-blob://account/container/blob` is needed, define a dedicated URI convention, resolver, and resource implementation. Production should prefer Managed Identity or DefaultAzureCredential with an appropriate workload identity; avoid storing long-lived account keys/SAS tokens in configuration. SAS URLs carry permissions and expiration and must be treated as secrets.

### 8.4. When to Use a Multi-Provider ResourceLoader?

Multiple ProtocolResolvers can be registered on the same DefaultResourceLoader:

~~~java
loader.addProtocolResolver(s3ProtocolResolver);
loader.addProtocolResolver(gcsProtocolResolver);
loader.addProtocolResolver(azureBlobProtocolResolver);
~~~

Each resolver recognizes its own scheme and returns the appropriate Resource. However, this is only a location resolution layer. If a service needs upload, delete, copy, list, versioning, or signed URL generation, use dedicated storage ports to express those operations.

Do not force providers with differing semantics into an overly weak interface. Interfaces can be split by use case:

- `DocumentReader`: opens streams and reads required metadata.
- `DocumentWriter`: writes objects and returns object identifier/version.
- `DocumentLister`: lists by prefix/page token.
- `DocumentLifecycle`: delete, archive, retention, or restore.
- `SignedDownloadUrlProvider`: generates temporary access URLs according to policy.
## 9. Read Resource vs. Write WritableResource

### 9.1. Resource Does Not Support Writing by Default

`Resource` focuses on access/reading. Spring has a `WritableResource` interface extending Resource, providing `isWritable()` and `getOutputStream()`. Some local implementations such as `FileSystemResource` support writing; this does not mean every cloud Resource supports upload.

With object storage, writing may involve:

- Will the object be overwritten?
- Is there a create-if-not-exists condition?
- Is it a small upload or a multipart upload?
- How are content type, metadata, tags, encryption, and checksum configured?
- Is there versioning or retention/object lock?
- When the output stream closes, is the upload committed or is there a finalize step?
- If the upload fails mid-way, are multipart parts aborted?
- Which ETag/version/generation does the caller receive?

If implementing `WritableResource`, clearly define the semantics of the output stream and when the upload actually completes. For many applications, a specialized port such as `DocumentStorage.store(key, input, metadata)` is safer and clearer.

### 9.2. Do Not Use File to Represent a Cloud Object

Some legacy libraries only accept `File`. If compatibility is required, download the object to a temporary file:

~~~java
Path temp = Files.createTempFile("cloud-resource-", ".bin");
try (InputStream input = resource.getInputStream()) {
    Files.copy(input, temp, StandardCopyOption.REPLACE_EXISTING);
}

try {
    legacyProcessor.process(temp.toFile());
} finally {
    Files.deleteIfExists(temp);
}
~~~

Examples also need to handle size limits, disk quotas, file permissions, cleanup when the process is killed, and safe filenames. Do not use this approach for large objects if the library can be updated to accept an InputStream/ReadableByteChannel.

## 10. Security and Tenant Isolation

### 10.1. Resource URI Is Not Authorization

Knowing the URI `s3://bucket/key` does not mean the caller has permission to read the object. Access is determined by IAM roles, bucket policies, KMS key policies, network controls, and provider controls.

The application needs to enforce:

- Environment-specific bucket/container allow-lists.
- Server-verified tenant prefixes or tenant-to-container mappings.
- Least-privilege object read permissions; do not grant list/write/delete if the use case only needs get.
- KMS decrypt permissions if the object uses SSE-KMS.
- Blocking client-supplied URIs pointing to out-of-scope buckets/accounts.
- Preventing users from choosing endpoints/hosts to avoid SSRF or accessing metadata services via arbitrary HTTP resolvers.

### 10.2. Do Not Put Secrets in Locations

Do not use URIs such as:

~~~text
s3://ACCESS_KEY:SECRET_KEY@bucket/key
https://bucket.s3.amazonaws.com/key?X-Amz-Signature=...
~~~

URIs containing credentials can leak into logs, metrics, exceptions, traces, or browser history. Use workload identity/credential providers for the SDK. If a signed URL is needed, generate it through a dedicated service, restricting method, object, expiration, and recipient; do not treat signed URLs as stable Resource identifiers.

### 10.3. Path Normalization and Object Keys

Object keys can contain slashes, spaces, and Unicode characters. Do not blindly apply file system normalization rules such as stripping `..` because object keys are provider-managed name strings. Instead:

1. Parse the URI according to RFC 3986.
2. Accept only defined schemes/authorities.
3. Decode the path strictly once according to convention.
4. Validate the bucket/container and tenant prefix against an allow-list.
5. Do not concatenate user input into endpoints/hostnames.
6. Preserve the validated object key as-is when calling the SDK.

If a tenant is only allowed to read the `tenant-a/` prefix, verify on the server that the key starts with the authenticated prefix. Do not rely on the URI merely containing a tenant ID string to grant access.

## 11. Performance, Caching, and Consistency

### 11.1. Streaming Instead of Loading Everything

For large objects:

- Use streams/byte channels and process in chunks.
- Close the stream early when the caller cancels or the parser finishes.
- Configure connection/read timeouts and cancellation aligned with request deadlines.
- Limit concurrent streams to avoid exhausting the HTTP connection pool or file descriptors.
- Use provider range reads when reading a slice of an object; the Resource interface has no standard range API.

For HTTP requests, do not hold a cloud stream open while waiting on user interaction. If the client response is cancelled, close the stream and release the connection.

### 11.2. Metadata and Existence Caching

`contentLength()`, `lastModified()`, and `exists()` may send HEAD requests. Calling them repeatedly on the same resource increases cost and latency. Metadata can be cached in the resource handle or a service-level cache, keeping in mind:

- The object may be overwritten or deleted.
- ETag is not always a content checksum (for example, multipart uploads or encryption).
- Version ID/generation identifies an immutable version better than the current key.
- Cache TTL introduces staleness when changes occur.
- 403 must not be cached as not-found.
- Cache keys must include provider/account/bucket/key and version if present.

By default, Resource is not a caching layer and does not guarantee an immutable snapshot. If reading an exact version is required, the locator must carry the version ID/generation or the adapter must accept the version explicitly.

### 11.3. Do Not Keep InputStream in Cache

Caching a Resource handle can be acceptable if the resource is immutable regarding its locator/client; caching an open InputStream is usually unsafe. An InputStream has its own cursor and lifecycle and cannot be reused across requests or threads. Open a new stream per read according to the implementation's contract and close it properly.

## 12. Error Mapping and Observability

### 12.1. Distinguishing Errors by Root Cause

| Error | Example | Handling Approach |
| --- | --- | --- |
| Not found | S3 404/NoSuchKey, Blob not found | Return not-found per business contract |
| Forbidden | IAM deny, bucket policy, KMS decrypt deny | Do not retry blindly; check identity and resource policy |
| Network timeout | Connect/read timeout | Bounded retry if operation is idempotent and deadline remains |
| Throttling | Request rate exceeds quota | Backoff + jitter, limit concurrency |
| Invalid URI | Invalid scheme, bucket, or key | Reject input; do not call provider |
| Serialization/processing | Parser cannot read content | Record data error; avoid infinite retries on the same bytes |
| Resource changed | Object overwritten/deleted between HEAD and GET | Use version/conditional read when a snapshot is needed |

Do not catch every exception and return `Optional.empty()` or `null`; doing so causes 403s, timeouts, and configuration bugs to be mistaken for missing resources.

### 12.2. Logging and Metrics

Log structurally with:

- Provider, log-approved bucket/container, and masked object key if sensitive.
- Operation: resolve, head, get, list, or write.
- Correlation ID, internal tenant ID, and provider request ID if available.
- Latency, bytes read, status/error code, and retry count.
- Cache hit/miss and open stream count if instrumented.

Do not log credentials, SAS tokens, presigned query strings, or document contents. Monitor p50/p95/p99 latency, HEAD/GET request counts, bytes, throttling, 4xx/5xx rates, stream leaks, and pool saturation. Micrometer can be used to export metrics into the application's observability system.
## 13. Testing the Resource Adapter

### 13.1. Unit Testing the URI Resolver

Verify:

1. `s3://bucket/key` creates the correct S3ObjectResource.
2. Other schemes return null so other resolvers handle them.
3. Missing bucket/key is rejected.
4. URIs with user info, port, query, or fragment are rejected.
5. Keys with slashes and percent-encoded characters are preserved per convention.
6. Invalid URIs do not trigger SDK requests.

### 13.2. Unit Testing S3ObjectResource with Mocks

Mock `S3Client` to verify:

- `getInputStream()` calls `GetObject` with the right bucket/key.
- The caller closes the stream and the response body is released.
- `exists()` returns false for 404 and does not turn 403 into false.
- `contentLength()`/`lastModified()` map metadata correctly.
- `getFile()` always reports it is not a local file.
- SDK errors are mapped to IOException/runtime exceptions per the contract.

### 13.3. LocalStack and Staging

LocalStack can help verify basic S3 flows locally/in CI: creating buckets, putting objects, resolving `s3://`, and reading content. However, do not assume an emulator fully simulates IAM policy evaluation, KMS key policies, cross-account access, VPC endpoints, versioning, lifecycles, Object Lock, or every AWS error code.

AWS staging should verify real workload roles, bucket policies, KMS encryption, Region, endpoints, and object-level permissions. Use test objects containing no sensitive data, cap costs, and clean up test resources after completion.

## 14. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `NoResourceFoundException` or resource treated as classpath | ProtocolResolver not registered on the loader in use | Inject the right `cloudResourceLoader` or integrate the resolver into ApplicationContext |
| `getFile()` throws FileNotFoundException | Cloud object is not a local file | Use `getInputStream()` or copy to a managed temporary file |
| `exists()` returns false even though the object exists | Principal lacks HEAD/GetObject permission or provider hides existence | Check IAM/bucket policy; distinguish 403 from 404 |
| `AccessDenied` | Missing IAM, bucket, KMS, or tenant prefix permission | Check role, resource policy, KMS key policy, and key |
| `Connection pool exhausted` when reading many objects | Streams not closed or concurrency too high | Use try-with-resources, limit concurrency, and monitor pool |
| HEAD succeeds but GET fails | Object changed, permissions differ, or network error at GET time | Handle GET errors; use version/conditional read if needed |
| Resource pattern finds no objects | ProtocolResolver resolves a single location, does not list wildcards | Implement a dedicated ResourcePatternResolver/provider listing |
| URI with spaces/Unicode produces wrong key | Inconsistent encoding/decoding | Normalize URI per RFC 3986 and test with real object keys |
| Signed URL expired | Temporary URL used as a long-term locator | Store bucket/key/version; generate signed URLs when access is needed |

## 15. Practice Exercises

1. Write a service that reads content from `classpath:`, `file:`, and `s3:` using the same method accepting `Resource`; explain why `getFile()` is not called.
2. Create `S3ObjectResource` with `getInputStream()`, `exists()`, `contentLength()`, `lastModified()`, and handle not-found/forbidden errors.
3. Write `S3ProtocolResolver` to parse `s3://bucket/key`; add tests for invalid URIs, query strings, and keys with Unicode.
4. Register the resolver in a dedicated `DefaultResourceLoader`, inject it with `@Qualifier`, and demonstrate that the default loader does not natively recognize the S3 scheme.
5. Read a large object via streaming and measure heap usage compared to `readAllBytes()`; verify the stream is closed on error/cancellation.
6. Design separate `DocumentReader` and `DocumentWriter` interfaces; explain why `Resource` does not replace upload/multipart APIs.
7. Compare AWS S3, Google Cloud Storage, and Azure Blob Storage in terms of locator, identity, metadata, versioning, and stream semantics.
8. Use LocalStack to test object reads, then test in staging with an IAM role and SSE-KMS.
9. Design a metadata cache with TTL and version-aware keys; define how overwrites/deletes and permission errors are handled.
10. Design tenant isolation for object URIs: bucket allow-list, prefix authorization, and preventing callers from accessing another tenant's objects.

**Completion criteria:** learners can explain Resource/ResourceLoader/ProtocolResolver, build a cloud URI resolver for one provider, read objects safely via streams, handle metadata and errors with proper semantics, distinguish read vs. write, and prove tenant access is controlled in tests.

## References

- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): Resource abstraction, ResourceLoader, and resource paths.
- [Spring Framework — Resource interface API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html): Resource contract.
- [Spring Framework — ResourceLoader API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/ResourceLoader.html): getResource and location prefixes.
- [Spring Framework — ProtocolResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/ProtocolResolver.html): extension point for custom protocols.
- [Spring Framework — DefaultResourceLoader API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/DefaultResourceLoader.html): registering protocol resolvers.
- [Spring Cloud AWS — S3 reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): S3 integration and abstractions by release.
- [AWS SDK for Java 2.x — Amazon S3 examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3.html): S3 client, GetObject, and metadata operations.
- [Google Cloud Storage — Java client](https://cloud.google.com/storage/docs/reference/libraries#client-libraries-install-java): Java SDK and object reads.
- [Azure Storage Blob — Java SDK](https://learn.microsoft.com/azure/storage/blobs/storage-blob-java-get-started): BlobClient, metadata, and streaming.

# Amazon S3-compatible endpoints, path-style access, and differences from AWS S3

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud to handle storage, messaging, data, identities, and permissions. During development or private-cloud deployment, an application may also need to connect to an object storage system supporting an **S3-compatible API**. However, supporting part of the S3 API does not mean that system has identical endpoints, permissions, signatures, features, and behaviors to Amazon S3.

This lesson focuses on three topics:

1. **S3-compatible endpoints:** API addresses of object storage services implementing part or most of the S3 protocol.
2. **Path-style and virtual-hosted-style addressing:** two ways of placing the bucket in the HTTP URL.
3. **Differences from AWS S3:** differences in SigV4, Region, APIs, permissions, encryption, versioning, lifecycle, checksums, consistency, and presigned URLs.

After this lesson, you will be able to configure AWS SDK for Java v2/Spring Cloud AWS to point to a custom endpoint, choose path-style when required by a provider, test uploads/downloads/presigned URLs, and evaluate compatibility before migrating an application to another object storage system.

> **Scope:** Examples use AWS SDK for Java v2 (`software.amazon.awssdk` packages) and modern Spring Cloud AWS (`io.awspring.cloud` namespace). Choose library versions compatible with your actual Spring Boot version. MinIO/local endpoints are development examples only; never use default credentials in production.

## 1. What does S3-compatible mean?

Amazon S3 exposes an object storage API to create buckets, upload/download objects, list keys, delete, manage multiparts, metadata, and many other capabilities. Some other object storage systems implement a **subset of S3-compatible APIs**, allowing AWS SDKs or S3 tools to connect to them.

Examples of systems that can expose an S3-compatible API:

- **MinIO:** object storage commonly deployed locally, in Kubernetes, or on private infrastructure.
- **Ceph Object Gateway (RADOS Gateway):** S3-compatible object storage interface within a Ceph cluster.
- **LocalStack:** emulates several AWS services, including S3, for development and testing.
- **Object storage services from other vendors:** may offer S3-compatible endpoints with their own feature scope and constraints.

**S3-compatible is not a guarantee that every AWS S3 API and behavior is supported.** A provider may support PUT/GET/LIST while lacking full support for Object Lock, conditional multipart completion, certain checksums, lifecycle filters, KMS integration, or AWS policy conditions.

### 1.1. Why is a custom endpoint needed?

Without an endpoint override, the AWS SDK automatically selects an AWS endpoint based on the Region. When connecting to MinIO or another S3-compatible service, the application must specify the service's **base endpoint**.

~~~text
AWS S3:
https://s3.ap-southeast-1.amazonaws.com

Local MinIO:
http://localhost:9000

S3-compatible service in a private network:
https://object-storage.internal.example
~~~

The addresses above are examples. The actual endpoint is provided by your infrastructure/provider; it can include scheme, hostname, and port. Never append the bucket or object key into the configured endpoint: the SDK routes bucket/key according to the addressing style.

### 1.2. Endpoint, bucket, and key are three separate components

| Component | Example | Role |
| --- | --- | --- |
| Endpoint | `http://localhost:9000` | API server the client connects to |
| Bucket | `training-files` | Container space holding objects |
| Object key | `documents/demo.txt` | Object identifier inside the bucket |

The endpoint is where you connect; bucket/key identify the target resource. **Never set the endpoint to `http://localhost:9000/training-files` and also ask the SDK to add the bucket**, as that can duplicate the path or break request signing.

## 2. Two addressing styles: virtual-hosted-style and path-style

When sending an S3 request, the bucket can sit in the **hostname** or in the **URL path**.

### 2.1. Virtual-hosted-style

The bucket is placed in the hostname:

~~~text
https://training-files.s3.ap-southeast-1.amazonaws.com/documents/demo.txt
        └──── bucket ────┘
~~~

With a custom endpoint, the pattern may look like:

~~~text
https://training-files.storage.example.com/documents/demo.txt
        └── bucket as subdomain ──┘
~~~

Some providers require wildcard DNS or routing rules so bucket subdomains resolve to the same service.

### 2.2. Path-style

The bucket is placed at the start of the path right after the hostname:

~~~text
https://s3.ap-southeast-1.amazonaws.com/training-files/documents/demo.txt
                                     └bucket─┘└──── object key ────┘
~~~

With local MinIO:

~~~text
http://localhost:9000/training-files/documents/demo.txt
                    └bucket─┘└──── object key ────┘
~~~

Path-style is often convenient for local development or endpoints that do not support bucket subdomains. The SDK must be told to place the bucket in the path to construct requests properly.

### 2.3. Comparing the two styles

| Criterion | Virtual-hosted-style | Path-style |
| --- | --- | --- |
| Where is the bucket? | In the hostname | In the URL path |
| Example | `https://bucket.storage.example/key` | `https://storage.example/bucket/key` |
| DNS requirements | May require wildcard/subdomain for buckets | Only needs the endpoint hostname |
| TLS certificate | Must be valid for hostnames containing the bucket | Can use a certificate for the shared endpoint |
| Localhost/port | Hard to simulate multiple subdomains without DNS setup | Easy to use `localhost:9000/bucket/key` |
| Provider compatibility | Depends on how the provider routes requests | Depends on provider path-style support |
| AWS S3 | Virtual-hosted-style is the standard form | Path-style is legacy/compatibility; check support per endpoint and bucket type |

### 2.4. Buckets with dots and TLS

If you use virtual-hosted-style with a bucket name containing dots, such as `my.files.backup`, the hostname has multiple labels:

~~~text
my.files.backup.s3.ap-southeast-1.amazonaws.com
~~~

A wildcard certificate like `*.s3.ap-southeast-1.amazonaws.com` may not match multi-level hostnames under TLS wildcard rules. This can cause HTTPS validation to fail in certain configurations. Path-style keeps the hostname at the common endpoint and puts the bucket in the path, avoiding that hostname issue if supported by the provider.

**Never disable certificate validation to work around TLS errors.** Choose the addressing style, bucket naming, and certificate aligned with your provider.

## 3. Configuring AWS SDK for Java v2 and Spring Cloud AWS

### 3.1. Dependencies

With Maven, import the Spring Cloud AWS BOM matching your Spring Boot version and add the S3 starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-aws.version` must be declared according to your project's compatibility matrix. The starter helps configure S3 clients and Spring integrations. When custom endpoints or addressing styles are needed, configure the appropriate client bean rather than merely changing the bucket name.

### 3.2. Custom properties for S3-compatible endpoints

You can separate endpoint and addressing style per Spring profile:

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      region:
        static: us-east-1

app:
  storage:
    bucket: training-files
    s3:
      endpoint: http://localhost:9000
      path-style: true
~~~

These are **application-defined properties**; `app.storage.s3.endpoint` and `path-style` are not standard property names across all Spring Cloud AWS versions. `us-east-1` locally is the Region used to sign requests per emulator config, not an indication that local data resides in that AWS Region.

AWS production can use a separate profile omitting any endpoint override so the SDK uses the standard Region endpoint. Never let local configuration get activated accidentally in production.

### 3.3. Creating `S3Client` with `endpointOverride` and `pathStyleAccessEnabled`

AWS SDK v2 provides `S3Configuration.pathStyleAccessEnabled(true)` to enable path-style addressing. `endpointOverride` specifies the base endpoint:

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

@Configuration(proxyBeanMethods = false)
public class CompatibleS3ClientConfiguration {

    @Bean
    public S3Client s3Client(
            @Value("${spring.cloud.aws.region.static}") String region,
            @Value("${app.storage.s3.endpoint}") String endpoint,
            @Value("${app.storage.s3.path-style:true}") boolean pathStyle) {

        return S3Client.builder()
                .region(Region.of(region))
                .endpointOverride(URI.create(endpoint))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .serviceConfiguration(
                        S3Configuration.builder()
                                .pathStyleAccessEnabled(pathStyle)
                                .build())
                .build();
    }
}
~~~

**Explanation:**

- `endpointOverride` replaces the default AWS endpoint with the configured endpoint.
- `region` is still required because the AWS SDK uses the Region when signing requests with Signature Version 4; many S3-compatible providers require a specific Region value or accept a default per their docs.
- `pathStyleAccessEnabled(true)` places the bucket in the URL path. If the provider supports virtual-hosted-style with proper DNS, you can set `false`.
- `DefaultCredentialsProvider` loads credentials from the AWS SDK provider chain. For local MinIO, supply dedicated access/secret keys via environment/profile; never use local keys in production.
- This bean illustrates **replacing/configuring the auto-configured client**. In real applications, ensure only one appropriate `S3Client` bean exists or use explicit `@Qualifier` annotations if multiple endpoints/clients are needed.

If the starter already auto-configures `S3Client`, declaring a custom bean may cause auto-configuration to back off depending on the mechanism/version. Check your Spring Cloud AWS version's auto-configuration conditions to avoid duplicate bean names or injecting the wrong client.

### 3.4. When is path-style unnecessary?

If the provider supports virtual-hosted-style, has wildcard DNS, and has valid certificates, you can disable path-style:

~~~java
.serviceConfiguration(
        S3Configuration.builder()
                .pathStyleAccessEnabled(false)
                .build())
~~~

Do not pick path-style merely because the URL is non-AWS. Check the provider's requirements: some services support only virtual-hosted-style, some only path-style, and others both. Verify hostname, TLS, routing, and actual request signing.

## 4. Credentials and Signature Version 4

### 4.1. S3-compatible endpoints can still require request signing

The AWS SDK typically signs S3 requests using **AWS Signature Version 4 (SigV4)**. An S3-compatible provider may support SigV4 yet still differ:

- The signing Region may be a specific region, a default value, or `auto` per provider documentation.
- The provider may require dedicated access/secret keys instead of AWS IAM roles.
- Session tokens or STS credentials may not be supported the same way as AWS.
- Some providers enforce particular rules on canonical requests, payload checksums, headers, or signing timestamps.
- Endpoint, host, and path must match exactly between the signed request and the sent request.

**Do not assume using the AWS SDK means using AWS IAM.** The SDK is only a protocol client; identity and permissions are governed by the provider behind the endpoint.

### 4.2. Credentials for local MinIO

Local environment example:

~~~powershell
$env:AWS_ACCESS_KEY_ID = "local-dev-access"
$env:AWS_SECRET_ACCESS_KEY = "local-dev-secret"
$env:AWS_REGION = "us-east-1"
$env:S3_ENDPOINT = "http://localhost:9000"
~~~

These values are illustrative for local development only. Real credentials should be created separately in MinIO with minimal permissions on a test bucket. Never commit them to Git, reuse them across environments, or log secrets.

### 4.3. Region and signature errors

If you encounter errors like `SignatureDoesNotMatch`, `AuthorizationHeaderMalformed`, or similar auth failures, check in order:

1. Endpoint scheme/host/port matches what the provider expects for its API endpoint.
2. Client Region matches the provider's signing Region.
3. Access key/secret match the endpoint's account/tenant.
4. Path-style vs. virtual-hosted-style matches how the provider routes buckets.
5. No proxy/gateway rewrites host/path/query after the request was signed.
6. System clock is accurate enough so the signing timestamp stays within the provider's skew tolerance.
7. Headers, checksums, and payload signing are compatible with the provider version.

Never work around signature errors by disabling TLS or sending unsigned requests when authentication is required.

## 5. Using the same Spring Boot service with environment-configured endpoints

A business service can keep calling `S3Client` for both AWS S3 and compatible endpoints, provided the APIs called are supported by the provider:

~~~java
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class ObjectStorageService {
    private final S3Client s3;
    private final String bucket;

    public ObjectStorageService(
            S3Client s3,
            @org.springframework.beans.factory.annotation.Value(
                    "${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public void upload(String trustedKey, byte[] content) {
        s3.putObject(
                PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(trustedKey)
                        .build(),
                RequestBody.fromBytes(content));
    }

    public byte[] downloadSmallObject(String trustedKey) {
        return s3.getObjectAsBytes(
                GetObjectRequest.builder()
                        .bucket(bucket)
                        .key(trustedKey)
                        .build())
                .asByteArray();
    }
}
~~~

The sample service uses `byte[]` for small objects; use streaming or Transfer Manager for large files. `trustedKey` must be obtained only after verifying user/tenant permissions. If a provider does not support an API called by the service, provide a fallback/adapter or disable that feature for that provider.

### 5.1. Multiple providers in the same application

If an application connects to both AWS and MinIO concurrently, define two explicitly named and qualified client beans:

~~~java
@Bean("awsS3Client")
S3Client awsS3Client() {
    return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .credentialsProvider(DefaultCredentialsProvider.create())
            .build(); // Default AWS endpoint for the Region.
}

@Bean("localS3Client")
S3Client localS3Client() {
    return S3Client.builder()
            .region(Region.US_EAST_1)
            .endpointOverride(URI.create("http://localhost:9000"))
            .credentialsProvider(DefaultCredentialsProvider.create())
            .serviceConfiguration(S3Configuration.builder()
                    .pathStyleAccessEnabled(true)
                    .build())
            .build();
}
~~~

This snippet focuses only on the two client configs; production code should separate properties per provider and let Spring manage lifecycles. When injecting, use `@Qualifier("awsS3Client")` or `@Qualifier("localS3Client")` to avoid ambiguity.

Never choose the provider based on user-supplied bucket/key strings. The provider/endpoint must be chosen by server configuration and trusted business logic.

## 6. Presigned URLs and addressing style

Presigned URLs are where endpoint and addressing-style discrepancies surface most visibly. The presigner signs **host + path + query + signed headers**. If the backend signs a URL pointing to `localhost` inside a container while the browser runs on the host machine or another computer, the URL will be unreachable.

### 6.1. Presigner must use the same endpoint and addressing style

When using a custom endpoint, configure `S3Presigner` consistently with `S3Client`:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration(proxyBeanMethods = false)
public class CompatibleS3PresignerConfiguration {

    @Bean
    public S3Presigner s3Presigner() {
        return S3Presigner.builder()
                .region(Region.US_EAST_1)
                .endpointOverride(URI.create("http://localhost:9000"))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .serviceConfiguration(
                        S3Configuration.builder()
                                .pathStyleAccessEnabled(true)
                                .build())
                .build();
    }
}
~~~

In production, never hard-code endpoint/Region as in this example; share the same configuration properties with the client. If the presigner uses virtual-hosted-style while the client uses path-style, generated URLs may have unexpected hosts/paths.

### 6.2. Clients must call the exact host the URL was signed for

Suppose the backend signs:

~~~text
http://localhost:9000/training-files/documents/a.txt?...signature...
~~~

If the browser must access it via another hostname, such as `https://storage.example.com`, **do not manually replace the host** in the URL after signing. The host is part of the canonical request; changing it invalidates the signature. Configure the presigner upfront with the exact hostname the client actually reaches, while ensuring DNS/TLS/routing lead to the same storage backend.

In Docker environments, `localhost` inside a container refers to **that container itself**, not the host machine or another container. If browsers run outside Docker, returned URLs must use a hostname/port reachable by the browser—such as a dev domain or reverse-proxied hostname. Proxies must not rewrite paths or hosts in ways that break the signature.

### 6.3. CORS is a separate layer

Browsers sending cross-origin PUT/GET requests are also subject to the endpoint/provider's CORS rules. Even with a valid presigned URL, browsers will block JavaScript from reading responses unless the provider configures:

- Allowed origin matching the frontend domain.
- Allowed methods (GET/PUT/HEAD) as needed.
- Allowed headers including `Content-Type` and required signed headers.
- Exposed response headers such as `ETag` when JavaScript must read them.

CORS does not replace signatures and does not grant object access permissions. When `curl` succeeds but a browser fails, inspect preflight/CORS in addition to IAM and signatures.

## 7. S3-compatible does not mean all S3 features are identical

### 7.1. Feature verification matrix

| Feature | AWS S3 | S3-compatible provider |
| --- | --- | --- |
| Basic PUT/GET/HEAD | Standard AWS API | Usually the compatibility baseline |
| ListObjectsV2, continuation token | Supported | Check API version and semantics |
| Multipart upload | Supported | Verify Create/UploadPart/Complete/Abort, part limits, and retries |
| Presigned URL SigV4 | Supported | Check signing Region, host, path-style, and signed headers |
| Conditional PUT (If-Match/If-None-Match) | Supported per specific API/conditions | May differ or lack full support |
| Versioning/delete markers | Supported | May be partially supported or behave differently |
| Lifecycle | Rich set of rule types | May support only a subset or differ in timing |
| SSE-S3/SSE-KMS/DSSE-KMS | Deep integration with S3/KMS | Does not automatically share KMS/key policy semantics |
| Object Lock/retention/legal hold | Supported | Provider-dependent; do not infer from API names |
| ACL/Object Ownership/Block Public Access | AWS semantics | May be incomplete or mapped differently |
| Event notifications | Integrated with many AWS services | Usually differs in destinations, payload, and retries |
| S3 Select, replication, access points | Specialized AWS features | Often unsupported or significantly different |

Before replacing AWS S3 with another provider, test the **specific APIs your application actually calls**, rather than just asking "is it S3-compatible?".

### 7.2. Differences that frequently impact applications directly

**Authentication and authorization**

AWS S3 uses IAM identity policies, bucket policies, SCPs, KMS key policies, and condition keys. S3-compatible services may use separate access keys, custom user/bucket policy models, or partial SigV4 support. Never copy AWS policies verbatim to another provider and assume identical semantics.

**Encryption**

AWS SSE-KMS integrates with AWS KMS and permissions like `kms:GenerateDataKey` and `kms:Decrypt`. Other providers may have their own KMS, service-managed default encryption, or only basic server-side encryption. Do not send AWS SSE-KMS headers if the endpoint does not support them.

**Versioning and lifecycle**

A provider might offer versioning without implementing delete markers like AWS; lifecycle might omit noncurrent version expiration or differ in execution timing. If business workflows depend on restoration, test actual PUT/DELETE/version-specific GET flows.

**Consistency and concurrency**

AWS S3 guarantees strong read-after-write consistency for common object APIs; do not assume every S3-compatible provider offers identical guarantees. For critical data, verify post-PUT/DELETE semantics, LIST behavior, conditional writes, and concurrent requests. Use a business database/index as the source of truth when transactions or strict ordering are required.

**Checksums and ETag**

ETag is not always MD5 on AWS S3, particularly with multipart uploads or certain encryption settings. Other providers may define ETags differently. When byte integrity is required, use mutually supported checksums and test end-to-end instead of treating ETag as a universal checksum.

**Metadata, tagging, and HTTP behavior**

Normalization of `Content-Type`, metadata headers, tags, `Content-Disposition`, `Cache-Control`, and error responses can vary. Clients should verify returned values via HEAD/GET, especially when migrating data across providers.

## 8. Distinguishing AWS S3 from Azure Blob Storage and Google Cloud Storage

AWS S3-compatible providers can share parts of the AWS SDK, whereas Azure Blob Storage and Google Cloud Storage have their own SDKs/APIs. The table below helps define abstraction boundaries:

| Business concept | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Container unit | Bucket | Storage account + container | Bucket |
| Object identifier | Object key | Blob name | Object name |
| Java SDK | AWS SDK v2 / Spring Cloud AWS | Azure Storage Blob SDK / Spring Cloud Azure | Google Cloud Storage Java client / Spring Cloud GCP |
| Large uploads | Multipart upload | Block blob: stage blocks + commit block list | Resumable upload |
| Pagination | ListObjectsV2 + continuation token | Paged iterable/continuation | Page token |
| Conditional writes | ETag conditions like If-Match | Blob request conditions | Generation/metageneration preconditions |
| Identity | IAM role/credentials | Managed identity + Azure RBAC | Service account + Google IAM |
| Customer-managed encryption | SSE-KMS | CMK via Key Vault per config | CMEK via Cloud KMS |
| Temporary links | Presigned URL | SAS | Signed URL |

A **domain interface** can share business operations like upload/download/delete, while implementations live in dedicated adapters:

~~~java
public interface ObjectStoragePort {
    StoredObject upload(
            String trustedKey,
            java.io.InputStream content,
            long contentLength,
            String contentType);

    void downloadTo(
            String trustedKey,
            java.io.OutputStream destination)
            throws java.io.IOException;

    void delete(String trustedKey);
}
~~~

`StoredObject` is an application-defined domain type. The AWS adapter uses `S3Client`/`S3Template`, the Azure adapter uses the Blob client, and the GCP adapter uses the Storage client. Avoid cramming every provider-specific feature like version IDs, lifecycle rules, retention, KMS keys, or event notifications into a tiny shared interface when their semantics are not equivalent.

## 9. Testing S3-compatible endpoints

### 9.1. Basic contract tests

For every target endpoint, maintain a contract test suite using an isolated bucket/prefix:

1. Create a test bucket or verify bucket existence under granted permissions.
2. PUT a small object with `Content-Type` and metadata.
3. HEAD the object and verify size/metadata.
4. GET the object and compare bytes/checksums against the source.
5. LIST by prefix and test continuation tokens across multiple pages.
6. DELETE the object and verify state according to provider semantics.
7. Test multipart upload/complete/abort if the application handles large files.
8. Generate and execute presigned GET/PUT URLs from an **actual client machine**, not solely inside the same container.
9. Test credential errors, wrong Region, wrong endpoint, wrong path-style, and invalid TLS certificates.

Not every provider supports all steps; document which capabilities are **required**, **optional**, or **unsupported** per adapter.

### 9.2. Local and real-provider testing matrix

| Environment | Purpose | What to watch |
| --- | --- | --- |
| Unit test/mocked SDK | Verify request construction, keys, and error handling | Does not verify wire protocol or real signatures |
| LocalStack | Local dev/testing of select AWS APIs | Emulation does not replace real AWS or every S3-compatible service |
| MinIO local | Verify endpoint, path-style, PUT/GET/LIST, multipart per version | Does not represent AWS IAM/KMS/lifecycle |
| Ceph RGW or target provider | Verify compatibility with the real endpoint | Test APIs, auth, Region, versioning, policies, and exact limits |
| AWS sandbox | Verify official AWS behavior | Use dedicated role/bucket, clean up data, and monitor cost |

### 9.3. Testing with AWS SDK v2

Simple contract test example (using a pre-provisioned test bucket):

~~~java
String key = "compat-test/" + java.util.UUID.randomUUID() + ".txt";
byte[] expected = "hello-compatible-storage".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("text/plain")
                .build(),
        RequestBody.fromBytes(expected));

var metadata = s3.headObject(b -> b.bucket(bucket).key(key));
if (metadata.contentLength() != expected.length) {
    throw new AssertionError("Content-Length mismatch");
}

byte[] actual = s3.getObjectAsBytes(b -> b
        .bucket(bucket)
        .key(key)).asByteArray();

if (!java.util.Arrays.equals(expected, actual)) {
    throw new AssertionError("Object content mismatch");
}
~~~

This illustrates core logic; in integration tests, use an assertion framework, random keys, and `finally`/teardown cleanup. If versioning is enabled on the bucket, cleanup may need to remove versions rather than just deleting the current key.

### 9.4. Testing presigned URLs through a browser

A test that only fetches a URL via `curl` does not fully validate browser flows. Check that:

- The returned URL uses a host the browser can resolve and reach.
- HTTPS/TLS certificates are valid in staging/production.
- The bucket sits in the right place in host/path per addressing style.
- Signed headers are transmitted intact by the browser.
- CORS permits the required origins, methods, and headers.
- Reverse proxies/DNS never rewrite host/path after signing.
- URLs are never logged or leaked beyond the authorized user.

**Never rewrite the host in a URL after presigning** just to "make it reachable by the browser"; configure the presigner with the right public/accessible endpoint upfront.

## 10. Common errors and diagnostics

| Symptom | Possible cause | Diagnostic step |
| --- | --- | --- |
| Connection refused | Wrong endpoint/port, service not running, container cannot route | Check endpoint from inside the exact runtime environment |
| DNS resolution failed | Bucket or endpoint hostname cannot resolve | Check DNS, virtual-hosted vs. path-style, and networking |
| TLS hostname mismatch | Certificate does not match bucket/subdomain hostname | Check addressing style and certificates; never disable TLS validation |
| 404 bucket/object | Bucket missing, wrong key, mismatched path-style | Inspect bucket, key, and actual HTTP URL |
| SignatureDoesNotMatch | Wrong Region, credentials, host/path, signed headers, or clock skew | Inspect SigV4 canonical request and endpoint |
| AuthorizationHeaderMalformed | Signing Region does not match provider expectations | Choose signing Region per endpoint documentation |
| InvalidRequest / unsupported header | Provider does not support a newer S3 header/API | Isolate capabilities; omit header only if the use case allows |
| Multipart Complete failure | Different ETag/part order/part size semantics or missing support | Test each multipart API; inspect part ETags and limits |
| Presigned URL unusable outside container | URL contains `localhost` or an internal hostname | Configure a browser-reachable endpoint before signing |
| Curl succeeds, browser fails | CORS/preflight issue or header blocked by browser | Check CORS, exposed `ETag`, and signed headers |
| HEAD/GET after PUT misses object | Consistency or API compatibility differs from expectations | Test provider semantics without assuming AWS parity |

When logging errors, capture operation, provider/endpoint alias, bucket/prefix per policy, HTTP status, provider request ID if returned, and error code. Never log access keys, secrets, full presigned URLs, or sensitive payloads.

## 11. Multi-environment deployment strategy

A Spring Boot application can reuse the same domain service while managing storage configuration per environment:

~~~text
local:
  endpoint = http://localhost:9000
  pathStyle = true
  credentials = local-only
  bucket = training-files

integration:
  endpoint = S3-compatible test endpoint
  pathStyle = per provider
  credentials = test environment secret
  bucket = test-bucket

production AWS:
  endpoint = default AWS endpoint for Region
  pathStyle = per appropriate AWS SDK config
  credentials = IAM workload role
  bucket = production bucket
~~~

**Never place production credentials or endpoints into committed local files.** While an endpoint may seem non-sensitive, altering it can redirect data to an unintended system; manage endpoints via controlled configuration, host allowlists, and profile isolation.

### 11.1. Pre-migration checklist before switching providers

- Are all required APIs supported: PUT/GET/HEAD/LIST/delete/multipart/conditional writes?
- Does the endpoint require virtual-hosted-style or path-style? Are DNS and TLS working?
- Are the SigV4 signing Region and credentials configured accurately?
- Do presigned URLs work from browsers/clients outside containers?
- Are CORS, signed headers, `Content-Type`, and `ETag` behavior compatible?
- Do versioning, lifecycle, encryption, retention, Object Lock, and event notifications share the required semantics?
- Do post-PUT/DELETE consistency and pagination under concurrent changes satisfy business needs?
- How does multipart handle part size limits, part counts, retries, and abort?
- Can the provider's IAM/policy model express required least privilege and auditing?
- Have contract tests passed against the **actual target endpoint** and an AWS sandbox for comparison?

## 12. Practice exercises

### Exercise A — Connecting to MinIO with path-style

Run an S3-compatible service locally and configure Spring Boot with endpoint `http://localhost:9000`, an appropriate signing Region, dedicated local credentials, and `pathStyleAccessEnabled(true)`. Create a bucket, upload a small file, HEAD, and download it. Inspect the request URL to confirm the bucket appears in the path.

### Exercise B — Comparing virtual-hosted-style

If your environment has wildcard DNS for bucket subdomains, disable path-style and test PUT/GET. Compare hostname, TLS certificate, and routing behavior. Test a bucket name containing dots to observe wildcard certificate effects.

### Exercise C — Presigned URLs outside containers

Generate a presigned GET URL from an app running in Docker. If the URL contains `localhost` or a container-only hostname, change the configuration to a public/dev-accessible endpoint **before signing**. Use a browser or `curl` on the host machine to download the file; confirm the URL is not altered after signing.

### Exercise D — Checking API compatibility

Write contract tests for PUT/GET/HEAD/LIST/DELETE against AWS S3 and an S3-compatible endpoint. If the application requires multipart, versioning, or conditional PUT, add dedicated tests for each feature. Document differences rather than treating all endpoints as identical.

### Exercise E — Multi-cloud adapter design

Define `ObjectStoragePort` in the domain layer. Implement an AWS adapter with `S3Client`, an Azure adapter with the Blob SDK, and a GCP adapter with the Storage SDK. Identify capabilities that must be enabled conditionally (versioning, lifecycle, encryption, presigned URLs, multipart) and design an explicit `unsupported` reporting mechanism.

### Self-check questions

1. Does an S3-compatible API guarantee support for every AWS S3 feature?
2. How does `endpointOverride` differ from bucket/key?
3. Where do path-style and virtual-hosted-style place the bucket in the URL?
4. When is path-style useful with MinIO/local endpoints?
5. Why is a Region still required when using a custom endpoint and SigV4?
6. Why must you never edit the host of a presigned URL after signing?
7. What issue can a bucket name containing dots hit with TLS wildcard certificates?
8. Why might the AWS SDK connect to an S3-compatible service while AWS IAM policies do not directly apply?
9. Which differences should be tested across multipart, versioning, lifecycle, and checksums?
10. Why should ETag not be treated as a universal MD5 checksum?
11. If a URL works in `curl` but fails in a browser, which layers should you inspect?
12. How do you distinguish endpoint/network errors from signature or permission errors?
13. Which operations belong in the domain interface and which belong in provider adapters?
14. Why are contract tests against the real target endpoint necessary rather than relying solely on LocalStack/MinIO?

**Expected outcome:** learners can configure Spring Boot/AWS SDK v2 to connect to an S3-compatible endpoint, choose path-style vs. virtual-hosted-style accurately, understand the roles of endpoint/Region/credentials/Signature V4, and identify compatibility boundaries before moving applications between AWS S3 and other object storage providers.

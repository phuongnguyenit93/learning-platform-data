# Amazon S3: Configuring S3 client, S3Template, and Spring Resource

## Learning objectives

In Spring Boot systems integrating managed services across AWS, Azure, and Google Cloud, **Amazon S3** is a common choice for storing documents, images, reports, and object data. This lesson focuses on **how Spring Boot connects to and operates on S3 via Spring Cloud AWS**, from the AWS SDK layer to Spring abstractions. After this lesson, you will be able to:

1. Add dependencies and configure the AWS Region, credentials, and bucket for a Spring Boot application.
2. Explain how Spring Cloud AWS creates/injects `S3Client` and when you need to configure the client manually.
3. Write a service using AWS SDK for Java v2 to PUT, GET, and HEAD objects.
4. Use `S3Template` to upload/download with less boilerplate code.
5. Read objects via Spring `Resource` using an `s3://bucket/key` address.
6. Choose the appropriate abstraction for streaming, metadata, testing, and secure deployment.

> **Version scope:** Examples use the `io.awspring.cloud` namespace of **modern Spring Cloud AWS**, together with AWS SDK for Java **v2** (`software.amazon.awssdk`). Choose a Spring Cloud AWS version compatible with your Spring Boot version according to the release compatibility matrix; older-generation APIs and starters may differ.

## 1. Three levels of abstraction for working with S3

Spring Cloud AWS does not replace the S3 API. It connects Spring Boot's auto-configuration mechanism with the AWS SDK and provides utility classes.

~~~mermaid
flowchart TD
    APP["Spring Boot service / controller"]
    APP --> SDK["AWS SDK v2: S3Client"]
    APP --> TEMPLATE["Spring Cloud AWS: S3Template"]
    APP --> RESOURCE["Spring: Resource / ResourceLoader"]
    TEMPLATE --> SDK
    RESOURCE --> S3["S3 Resource integration"]
    S3 --> SDK
    SDK --> HTTP["AWS Signature V4 + HTTP"]
    HTTP --> CLOUD["Amazon S3 bucket / object"]
~~~

| Usage approach | Level of detail | Best suited for |
| --- | --- | --- |
| `S3Client` | Explicit AWS SDK request/response, full control over API and metadata | PUT/GET/HEAD/LIST, conditional requests, specialized S3 operations |
| `S3Template` | Spring-idiomatic utility class, reduces boilerplate | Routine object upload/download in services |
| Spring `Resource` | Unified resource-reading interface via `s3://` | Reading config files, templates, static content, or streams like other `Resource`s |

An application can use all three approaches. For example: `S3Template` for standard uploads, `S3Client` when advanced metadata/conditions are needed, and `ResourceLoader` when a component only requires a `Resource` interface.

To make this concrete, assume the application has a bucket **`training-app-private-files`** in Region `ap-southeast-1`, with key `documents/demo-001.txt`. This is an illustrative name; replace it with the actual bucket for your environment.

## 2. Adding the Spring Cloud AWS S3 starter

### 2.1. Maven

In a Maven project, declare the **BOM** to align Spring Cloud AWS library versions and add the S3 starter:

~~~xml
<properties>
    <!-- Choose a version compatible with the Spring Boot version in use. -->
    <spring-cloud-aws.version>COMPATIBLE_VERSION</spring-cloud-aws.version>
</properties>

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

`COMPATIBLE_VERSION` is an **intentional placeholder** and must be replaced with an appropriate release version before building. Do not mix legacy Spring Cloud AWS artifacts (`org.springframework.cloud`/`com.amazonaws` from earlier generations) with the AWS SDK v2 code samples in this lesson.

The S3 starter brings in S3-related auto-configuration and supporting components such as `S3Template`; unless you have special requirements, you do not need to write a custom `@Bean S3Client` upfront.

### 2.2. Configuring Region and bucket

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    prefix: documents/
~~~

Here:

- `spring.cloud.aws.region.static` defines the AWS Region for the client configured by Spring Cloud AWS; the value must match the bucket's Region.
- `S3_BUCKET_NAME` is an environment variable provided by the runtime environment; do not put a hardcoded production bucket name into examples that may be copied widely.
- `app.storage.*` is **custom application-named configuration**, not a built-in property of the S3 starter.
- If there are multiple buckets, declare bucket names by purpose, such as `app.storage.private-bucket` and `app.storage.archive-bucket`, or manage them through a `@ConfigurationProperties` class.

The bucket must already exist and the application's identity must have appropriate permissions. The starter **does not automatically make a private bucket public**, nor does it create buckets by default every time the service starts.

### 2.3. Credentials: using the AWS SDK default provider chain

AWS SDK v2 has the **Default Credentials Provider Chain**, retrieving credentials from supported sources such as runtime identity (an IAM role on the workload), environment variables, system properties, or an AWS shared profile. Configuration details depend on the environment:

| Environment | Appropriate identity supply | Notes |
| --- | --- | --- |
| Development machine | Configured AWS CLI/SDK profile, SSO/temporary credentials | Run via a personal profile for the test environment |
| ECS | IAM **task role** | Do not confuse the task role with the execution role |
| EC2 | IAM instance profile | Scope permissions strictly to the service |
| EKS | IAM Roles for Service Accounts or EKS Pod Identity (depending on deployment) | Map permissions to the appropriate Kubernetes service account/pod |
| CI/CD | OIDC federation and short-lived role | Avoid storing long-lived AWS keys in pipelines |

Example of selecting a profile when running locally:

~~~powershell
$env:AWS_PROFILE = "dev-sandbox"
$env:S3_BUCKET_NAME = "training-app-private-files"
~~~

These are environment variables for the **PowerShell session**, not secrets. The `dev-sandbox` profile must already be validly configured beforehand. Do not put real `accessKey`/`secretKey` values into `application.yml`, a Git repository, or documentation examples. For production, prefer roles or workload identities and least-privilege policies.

### 2.4. Granting IAM permissions suited to the operations

Example policy attached to a backend role that is only allowed to list and read/write under the `documents/` prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDocumentKeys",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::training-app-private-files",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["documents/", "documents/*"]
        }
      }
    },
    {
      "Sid": "ReadWriteDocumentObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::training-app-private-files/documents/*"
    }
  ]
}
~~~

**Distinguishing bucket ARN and object ARN:** `s3:ListBucket` binds to `arn:aws:s3:::bucket`, while `s3:GetObject`/`s3:PutObject` require `arn:aws:s3:::bucket/key` or a key pattern. `s3:prefix` in the LIST statement only filters which keys may be listed—it **does not restrict** GET/PUT permissions; object-level restriction belongs in the ARN of the next statement.

`s3:ListBucket` is not required for every GET/PUT; grant it only if the application genuinely needs LIST or needs to distinguish non-existent objects. If the bucket uses **SSE-KMS**, you may also need permissions on the KMS key and need to check the KMS key policy. Backend IAM permissions also **do not replace** user/tenant checks at the business layer.

## 3. Using `S3Client` provided by Spring Cloud AWS

### 3.1. Injecting the client and performing PUT / GET / HEAD

Once the starter and appropriate configuration are in place, you can inject `software.amazon.awssdk.services.s3.S3Client` into a Spring service constructor.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class S3DocumentClientService {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentClientService(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String uploadSmallText(String text) {
        // Key name is server-generated, not taken from arbitrary client parameters.
        String key = "documents/" + UUID.randomUUID() + ".txt";
        byte[] body = text.getBytes(StandardCharsets.UTF_8);

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("text/plain; charset=UTF-8")
                .metadata(Map.of("source", "spring-boot"))
                .build();

        s3.putObject(request, RequestBody.fromBytes(body));
        return key;
    }

    public HeadObjectResponse inspect(String key) {
        requireDocumentKey(key);
        return s3.headObject(HeadObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build());
    }

    public void streamDownload(String key, OutputStream target)
            throws IOException {
        requireDocumentKey(key);
        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();

        try (ResponseInputStream<GetObjectResponse> source =
                     s3.getObject(request)) {
            source.transferTo(target);
        }
    }

    private static void requireDocumentKey(String key) {
        if (key == null || !key.startsWith("documents/")) {
            throw new IllegalArgumentException("Key is outside the documents/ prefix");
        }
    }
}
~~~

**How to read the code:**

- `S3Client` is a **synchronous SDK client** injected by Spring. Keep and reuse the client; do not create a new client for every request.
- `putObject` uploads the full content. `RequestBody.fromBytes` is suitable for **small files**; for large objects, use size-bounded streaming, multipart upload, S3 Transfer Manager, or presigned URLs.
- `headObject` returns only metadata (for example `contentLength()`, `contentType()`, `metadata()`) without downloading the body.
- `getObject` returns a `ResponseInputStream`, so the snippet uses try-with-resources to close the connection even if an error occurs. `transferTo` copies to the target output stream without attempting to read the entire object into a single byte array.
- The `startsWith("documents/")` check illustrates restricting key format; it is **not an ownership check**. Before calling the service, the API layer must verify that the user is allowed to access that object.
- `metadata(Map.of("source", "spring-boot"))` creates user metadata; over HTTP, S3 represents this with the `x-amz-meta-source` header.

For example, a controller call can map `invoiceId` to a key in the database after verifying permissions, then pass the **verified key** to the service. Avoid APIs that directly accept `?key=documents/other-tenant/...`.

### 3.2. When do you need to configure `S3Client` manually?

Auto-configuration suits most applications. Providing your own `S3Client` bean is an option when you need custom SDK settings such as timeouts, an HTTP client, an S3-compatible endpoint, or a non-default authentication mechanism.

Example of a bean customizing timeout while still using the default provider chain:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class CustomS3ClientConfig {
    @Bean
    public S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(30))
                        .build())
                .build();
    }
}
~~~

This is an **alternative to the auto-configured `S3Client`** and is not necessary in a typical application. When creating a bean manually like this, you are responsible for keeping Region/credentials/endpoint aligned with the rest of your configuration. If you need multiple clients for different purposes, specify clear bean names/`@Qualifier` annotations to avoid injecting the wrong one. Check the specific configuration options for your Spring Cloud AWS version when advanced customization is required.

**Note on the credential provider:** `DefaultCredentialsProvider` cannot invent credentials on its own. If no valid identity is found, S3 calls will fail even though Spring started up successfully.

## 4. Using `S3Template`: a simpler Spring-style API

`io.awspring.cloud.s3.S3Template` is an abstraction supporting common S3 operations. The S3 starter can auto-configure `S3Template` based on the AWS SDK and existing configuration.

### 4.1. Upload/download with `S3Template`

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import io.awspring.cloud.s3.S3Template;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class S3TemplateDocumentService {
    private final S3Template s3Template;
    private final String bucket;

    public S3TemplateDocumentService(
            S3Template s3Template,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Template = s3Template;
        this.bucket = bucket;
    }

    public void upload(String key, InputStream source) {
        requireDocumentKey(key);
        s3Template.upload(bucket, key, source);
    }

    public void downloadTo(String key, OutputStream destination)
            throws IOException {
        requireDocumentKey(key);

        Resource resource = s3Template.download(bucket, key);
        try (InputStream source = resource.getInputStream()) {
            source.transferTo(destination);
        }
    }

    private static void requireDocumentKey(String key) {
        if (key == null || !key.startsWith("documents/")) {
            throw new IllegalArgumentException("Invalid key");
        }
    }
}
~~~

Here:

1. `s3Template.upload(bucket, key, InputStream)` streams the input data. Stream ownership and when to close it must be clearly defined in the **calling code**; in this example, the caller is responsible for closing `source` after upload completes.
2. `s3Template.download(bucket, key)` returns a readable resource abstraction. The code calls `getInputStream()` to transfer data to `OutputStream`.
3. This usage is shorter than the SDK because you do not have to build `PutObjectRequest`/`GetObjectRequest` for each operation.
4. When you need conditional writes (`If-None-Match`), checksum control, tagging, specialized metadata, or APIs that `S3Template` does not expose directly, using `S3Client` (or another appropriate API) is clearer.

**Important:** An `InputStream` does not automatically become validated data. The controller/service must still enforce size limits, true format verification, business permissions, and concurrent upload limits. Do not let an HTTP request freely choose the bucket or key.

### 4.2. What if custom metadata is needed?

The `S3Client` example sets `Content-Type` and user metadata very explicitly on `PutObjectRequest`. `S3Template` supports metadata APIs depending on the version, though specific overloads may vary across Spring Cloud AWS releases. If a requirement demands exact metadata control or less common S3 options, using `S3Client` as in section 3 is less ambiguous.

A practical design rule:

- Choose `S3Template` for standard object read/write *use cases*.
- Choose `S3Client` for features tied to request/response details or specific S3 behaviors.
- Both can be injected into separate services; avoid writing numerous wrappers that merely rename methods without adding business checks, error observability, or policies.

## 5. Using Spring `Resource` to read S3 objects

Spring Framework provides the `org.springframework.core.io.Resource` interface to read resources from classpath, filesystem, URLs, and other sources. Spring Cloud AWS integrates S3 into this mechanism, allowing an object to be represented by an address:

~~~text
s3://training-app-private-files/documents/demo-001.txt
      └──────── bucket ────────┘└─────── object key ────────┘
~~~

The `s3://...` address is an S3-protocol **resource location**, not a public HTTP URL. Access still goes through the AWS SDK and the application's IAM permissions.

### 5.1. Reading a known resource with `@Value`

In an application with S3 resource integration enabled, you can inject a resource using a fixed address:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class WelcomeTextProvider {
    private final Resource welcomeText;

    public WelcomeTextProvider(
            @Value("s3://training-app-private-files/templates/welcome.txt")
            Resource welcomeText) {
        this.welcomeText = welcomeText;
    }

    public String loadText() throws IOException {
        try (var input = welcomeText.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

This example reads a **small** template. For large files, process line-by-line/stream instead of calling `readAllBytes()`. Injecting `Resource` usually creates only a **handle representing the resource location**; the actual content is read when `getInputStream()` is called, so credential, permission, or network errors can still surface at read time.

### 5.2. Dynamic addresses with `ResourceLoader`

When the bucket/key is determined at runtime, use `ResourceLoader` instead of a static `@Value` string:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class S3ResourceReader {
    private final ResourceLoader resourceLoader;
    private final String bucket;

    public S3ResourceReader(
            ResourceLoader resourceLoader,
            @Value("${app.storage.bucket}") String bucket) {
        this.resourceLoader = resourceLoader;
        this.bucket = bucket;
    }

    public void copyTo(String trustedKey, OutputStream target)
            throws IOException {
        if (trustedKey == null
                || !trustedKey.startsWith("documents/")) {
            throw new IllegalArgumentException("Key is outside the documents/ area");
        }

        Resource resource = resourceLoader.getResource(
                "s3://" + bucket + "/" + trustedKey);

        try (InputStream input = resource.getInputStream()) {
            input.transferTo(target);
        }
    }
}
~~~

This approach is useful when a service already has APIs accepting `Resource` (such as text processing, template reading, data parsing, or file conversion pipelines). The calling code does not need to know `GetObjectRequest` details to obtain a stream.

**Condition:** Resolution of the `s3://` protocol must be provided and enabled by the current Spring Cloud AWS starter/auto-configuration. If the resolver is not registered, Spring may fail to recognize this location as an S3 resource. In that case, check dependencies, versions, and auto-configuration; do not work around it by randomly switching to `https://` because HTTP URLs follow a different access mechanism.

### 5.3. Limitations of `Resource`

Do not treat `Resource` as a local file:

| Operation | S3 caveat |
| --- | --- |
| `getInputStream()` | May open a network connection, incur latency, and raise S3 errors; must close the stream |
| `exists()` or `contentLength()` | May require a HEAD call or network API; not a free check |
| `getFile()` | Typically unsupported; an S3 object has no `java.io.File` on the application's disk |
| `getURL()` | Does not guarantee a public/accessible HTTPS URL |
| Multiple reads | May trigger multiple GET requests, adding latency and cost |
| Writing | Use write capability only if supported by the resource implementation/version in use; for explicit uploads, prefer `S3Template` or `S3Client` |

If a framework requires a `java.io.File`, consider downloading the object to an application-managed **temporary file** and cleaning it up after use. That introduces disk I/O overhead and is no longer a pure streaming operation.

## 6. Choosing an abstraction in real-world scenarios

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| Backend uploading small images with mandatory metadata and `Content-Type` | `S3Client` | Explicit configuration of `PutObjectRequest` attributes |
| Service uploading/downloading documents by verified key | `S3Template` | Concise code focused on the use case |
| Tool reading CSV/templates via a common `Resource` interface | `ResourceLoader` | Abstracts away the reading source |
| Need to check ETag/version, conditional PUT, or tagging | `S3Client` | Full AWS request/response model |
| Large files via browser | Presigned URL or suitable multipart/transfer solution | Reduces data transfer and memory load on the backend |
| Batch processing service | Reused client + concurrency limits + pagination | Avoids creating a client per object and loading entire listings into RAM |

A document-management application flow can be organized as follows:

~~~mermaid
sequenceDiagram
    actor User as User
    participant API as Spring Boot API
    participant DB as Business database
    participant S3 as Private S3 bucket

    User->>API: Request to download document #42
    API->>DB: Verify user and fetch key
    DB-->>API: Authorized key
    API->>S3: S3Client / S3Template / Resource GET
    S3-->>API: Stream object content
    API-->>User: Stream document
~~~

At the key-lookup step, the backend must verify permissions per user/tenant. Having `s3:GetObject` on the S3 role does not decide which documents an application user is allowed to view.

## 7. Common configuration errors

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Cannot create `S3Client` or `S3Template` bean | Missing starter, incompatible version, auto-configuration disabled | Check dependencies and Spring Boot configuration |
| `Unable to load credentials` | SDK cannot find a valid profile/role/token | Check runtime identity; avoid adding real keys to source code |
| `AccessDenied` (403) | IAM/bucket policy/permission boundary/SCP/KMS or permission condition | Verify action, bucket/object ARN, explicit deny, and KMS |
| `NoSuchKey` (404) | Wrong bucket/key or object has been deleted | Log sanitized bucket/key; check exact key, case-sensitivity |
| Wrong Region, redirect, or `PermanentRedirect` | Client sends request to a mismatched Region | Check actual bucket Region and client configuration |
| `getResource("s3://...")` fails to read S3 | Missing S3 resource resolver or version mismatch | Check starter, auto-configuration, and location format |
| `OutOfMemoryError` during upload/download | Using `byte[]`/`readAllBytes` with large objects | Stream, multipart/transfer, limit size and concurrency |
| Slow or dropped downloads | Timeout, network, connection pool, too many open streams | Reuse client, close responses, configure appropriate timeout/retry |
| File saved but browser handles it wrongly | Incorrect `Content-Type`/`Content-Disposition` | Set metadata according to the validated actual format |
| Receiving 403 on HEAD for a non-existent key | Missing `s3:ListBucket` can cause S3 to return 403 instead of 404 | Do not conclude an object definitely exists based solely on 403 |

### Distinguishing startup errors from S3 call errors

Successfully creating an `S3Client` bean **does not prove** the application has permission to access the bucket. Many errors only occur when calling `getObject`, `headObject`, or `putObject`. Therefore, include integration checks that actually call S3 in a test environment, in addition to testing Spring context startup.

When logging errors, record the **operation**, bucket/key per security policy, request ID, and AWS error code if available. Avoid logging access keys, tokens, full presigned URLs, or sensitive file contents.

## 8. Integration testing without depending on production data

A three-layer strategy:

1. **Unit test:** mock `S3Client` or the application's abstraction to verify key generation, business permission checks before GET, and error handling. Mocks do not validate real IAM policies.
2. **Local integration test:** use an S3-compatible emulator such as LocalStack via Testcontainers when appropriate. Configure a dedicated test endpoint/profile; create a test bucket, PUT/GET/HEAD an object, and clean up resources.
3. **Integration test on an AWS sandbox:** run with a real IAM role and test bucket, verifying least privilege, encryption, Region, metadata, 403/404 responses, and network scenarios. Emulators cannot fully replicate IAM/KMS policies or every managed AWS behavior.

Example configuration **only for a test/local profile** if the application uses an S3 emulator at `localhost:4566`:

~~~yaml
# Example configuration for the local profile, do not use in production
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      s3:
        endpoint: http://localhost:4566

app:
  storage:
    bucket: local-training-files
~~~

The actual Testcontainers endpoint may have a dynamic host/port; tests must inject that address into runtime configuration. Emulators may also require **path-style addressing** or other compatibility settings depending on the version. Only force the endpoint in the test profile to prevent production applications from accidentally pointing to localhost.

**Lab checklist:** create test bucket → authenticate via simulated credentials/sandbox role → upload small file with `S3Client` → read metadata with HEAD → download with `S3Template` → read same object via `ResourceLoader` → compare bytes → run negative case with missing permission in AWS sandbox → clean up objects.

## 9. Comparison with Azure and Google Cloud

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module aims to help learners integrate Spring Boot with managed services from AWS, Azure, and Google Cloud. When porting an object storage design to another provider, you can keep the **business contract** such as `ObjectStorageService.put(key, bytes)` or `get(key)`, while the adapter layer changes.

| Application concept | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Object operations client | `S3Client` (AWS SDK v2) | Azure Storage Blob SDK client | Google Cloud Storage Java client |
| Spring abstraction | `S3Template` and S3 `Resource` via Spring Cloud AWS | Corresponding Spring Cloud Azure integration | Corresponding Spring Cloud GCP integration |
| Workload identity | IAM role / SDK credential chain | Managed Identity / Azure Identity | Service account / Application Default Credentials |
| Object container unit | Bucket | Storage account + container | Bucket |
| Time-limited path sharing | Presigned URL | SAS | Signed URL |

Do not copy property namespaces or authorization behaviors verbatim across providers. For example, `s3://` is a resource location specific to S3 integration; an Azure or GCP adapter must use the API/resource scheme supported by its corresponding library. Provider comparisons should focus on **authentication, permissions, metadata, consistency, cost, and testing**, not just upload/download method names.

## 10. Practice exercises

**Exercise A — Observing auto-configuration.** Create a Spring Boot application with the S3 starter, configuring `spring.cloud.aws.region.static` and `app.storage.bucket`. Inject `S3Client` into a service. Use a development profile with valid credentials to PUT a test object; record its key and content type. Explain why you do not need to declare an `S3Client` bean manually for basic use cases.

**Exercise B — Comparing three reading approaches.** Upload `documents/lab.txt` with content `Hello S3`. Download it sequentially using:

- `S3Client.getObject(...).getInputStream()/ResponseInputStream`.
- `S3Template.download(...).getInputStream()`.
- `ResourceLoader.getResource("s3://bucket/documents/lab.txt").getInputStream()`.

Verify that all three byte results match and close all input streams. Observe the number of network requests if tracing is available in the test environment.

**Exercise C — Error and permission handling.** Using a test bucket, try accessing a non-existent key and a key for which the IAM role lacks GET permission. Compare the error codes; explain why `403` is not sufficient to conclude an object exists. Verify `s3:GetObject` on the object ARN and `s3:ListBucket` on the bucket ARN.

**Exercise D — Designing a multi-cloud service.** Write a business interface `ObjectStoragePort` with `upload`, `download`, and `inspectMetadata`. Sketch an AWS adapter implemented with `S3Client` and another adapter for Azure or GCP. Point out which attributes are common across clouds and which are provider-dependent.

### Self-check questions

1. What is the difference between an `S3Client` bean auto-created by Spring Cloud AWS and a manually configured bean?
2. Why must you choose a Spring Cloud AWS BOM compatible with your Spring Boot version?
3. When should you use `S3Template` instead of calling `S3Client` directly?
4. Why can injecting a `Resource` succeed while `getInputStream()` still throws an error?
5. Why is `Resource.getFile()` not suitable for an object stored on S3?
6. How can you read a large object without loading its entire content into RAM?
7. Why does a backend IAM policy not replace user permission checks at the controller/service layer?
8. How would you test differences in credentials, IAM, metadata, and Region behavior between an emulator and an AWS sandbox?

After this lesson, learners should be able to establish a Spring Boot → S3 connection using Spring Cloud AWS, choose the right `S3Client`/`S3Template`/`Resource` for each need, handle streams properly, and organize testing as well as access identities per deployment environment.

# Integrating Object Storage Service via the SDK or a Still-Suitable Starter

## 1. Problem Statement and Objectives

An order-management Spring Boot application needs to store PDF invoices, product images, and customer attachments. The application must upload/download objects, keep buckets private, restrict access permissions per workload, and provide file download paths to users without exposing AccessKeys.

Alibaba Cloud **Object Storage Service (OSS)** provides buckets for storing objects. A Java application can integrate with OSS in three ways:

- **OSS Java SDK**: calls product APIs directly; the application creates the client, configures credentials, region, endpoint, and manages the lifecycle.
- **Aliyun OSS Spring Boot Starter**: provides auto-configuration for common operations in Spring Boot; suitable when the starter version and the APIs it wraps are compatible with the application.
- **Presigned URL**: the backend uses the SDK to generate a signed, time-limited URL; browsers/mobile clients transfer files directly to OSS without holding cloud credentials.

This lesson belongs to the **Alibaba Cloud** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module teaches practical Spring Boot integration with managed services from AWS, Azure, Google Cloud, and Alibaba Cloud through their respective libraries; learners need to configure identity/permissions, access storage, messaging, and data, protect secrets, write integration tests, and evaluate differences across providers.

After completing this lesson, you will be able to:

1. Choose between SDK V1, SDK V2, or a starter based on maintenance status and compatibility.
2. Configure the OSS client with region, endpoint, and Signature Version 4.
3. Integrate RAM role/STS credentials into Spring Boot and automatically refresh credentials.
4. Upload/download objects, handle metadata, and manage the client lifecycle.
5. Choose among simple upload, multipart/resumable upload, or presigned URLs.
6. Restrict RAM permissions, protect buckets/objects, and prevent data overwrites.
7. Test the OSS adapter and diagnose AccessDenied, SignatureDoesNotMatch, endpoint, and timeout errors.

## 2. Choose the SDK or the Spring Boot Starter?

### 2.1. Three Options and Usage Scope

| Option | Characteristics | When Suitable |
| --- | --- | --- |
| **OSS Java SDK V1** (artifact **aliyun-sdk-oss**) | Mature Java API with extensive examples for upload/download, multipart, resumable, metadata, and presigned URLs; requires manual client configuration | Production applications needing a battle-tested API, or upgrading an existing V1 integration |
| **OSS Java SDK V2** (artifact **alibabacloud-oss-v2**) | Redesigned API, new builder and request models, sync/async clients; OSS docs currently mark SDK 2.0 as **preview** | Projects that can evaluate previews, want to try the new API, and have integration tests/an upgrade path |
| **Aliyun OSS Spring Boot Starter** (artifact **aliyun-oss-spring-boot-starter**) | Spring Boot auto-configuration; published artifact version is **1.0.0**, which pulls in OSS Java SDK V1 | Existing applications already using the starter that have verified compatibility with their running Spring Boot version |

As of **24/11/2026**:

- OSS Java SDK V1 documentation was updated in 2026 and specifies the dependency **com.aliyun.oss:aliyun-sdk-oss:3.18.4**.
- OSS Java SDK V1 supports Signature V4; documentation recommends V4 because Signature V1 is being phased out.
- OSS Java SDK V2 documentation still carries the **preview** label; Maven Central lists version **0.6.1** released on 20/10/2026.
- **aliyun-oss-spring-boot-starter** on Maven Central is **1.0.0**; the starter's POM depends on **aliyun-sdk-oss**. The project README only states Spring Boot 2 and above, offering no detailed compatibility matrix proving Boot 3.x/4.x support.

Therefore, this lesson uses **OSS Java SDK V1 + Signature V4** to demonstrate an integration with complete API documentation. SDK V2 is introduced so learners understand its preview status and how to evaluate it before adoption. The starter is a conditional option for existing applications; do not add it to a new project merely because its name includes "Spring Boot".

### 2.2. Dependency Coordinates

**OSS Java SDK V1:**

~~~xml
<dependency>
    <groupId>com.aliyun.oss</groupId>
    <artifactId>aliyun-sdk-oss</artifactId>
    <version>3.18.4</version>
</dependency>
~~~

From SDK V1 **3.17.4 and above**, Signature V4 is supported per the signature upgrade guide. Examples in this lesson use 3.18.4. When creating a real project, check the latest release, Java baseline, and dependency tree before pinning a version.

**OSS Java SDK V2:**

~~~xml
<dependency>
    <groupId>com.aliyun</groupId>
    <artifactId>alibabacloud-oss-v2</artifactId>
    <version>0.6.1</version>
</dependency>
~~~

SDK V2 uses different packages from SDK V1, such as **com.aliyun.sdk.service.oss2**. Do not mix V2's OSSClient with V1's com.aliyun.oss.OSS in the same configuration class.

**Aliyun OSS Spring Boot Starter:**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>aliyun-spring-boot-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>aliyun-oss-spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

The **aliyun-spring-boot-dependencies** BOM belongs to the **aliyun-spring-boot** project, not **spring-cloud-alibaba-dependencies**. The OSS 1.0.0 starter POM pulls in **com.aliyun.oss:aliyun-sdk-oss**. Before using it, inspect the effective POM, dependency tree, auto-configuration, and samples for that exact starter version. Do not assume the starter's properties or bean names match the custom properties defined in this lesson.

### 2.3. Integration Selection Decision Tree

~~~mermaid
flowchart TD
    A{"Does the project already use Aliyun OSS Starter?"}
    A -->|"Yes"| B{"Has Starter 1.0.0 passed tests on current Boot/JDK?"}
    B -->|"Yes"| C["Keep starter and control transitive SDK"]
    B -->|"No"| D["Replace with direct SDK after testing"]
    A -->|"No"| E{"Is SDK V2 preview acceptable?"}
    E -->|"Yes"| F["Evaluate OSS Java SDK V2 in staging"]
    E -->|"No"| G["OSS Java SDK V1 + Signature V4"]
    C --> H["Isolate adapter and test OSS"]
    D --> H
    F --> H
    G --> H
~~~

If an application only needs to upload/download objects, using the SDK directly is usually sufficient. A starter adds value when it genuinely reduces boilerplate configuration and is maintained for your Spring Boot version. Never let an outdated starter block platform upgrades.

## 3. Preparing the Bucket, Region, and Permissions

### 3.1. Creating the Bucket and Recording Parameters

Before writing code:

1. Activate OSS and create a bucket in the chosen region.
2. Record the **bucket name**, **region ID**, and appropriate endpoint.
3. Keep the bucket/object ACL set to **private** unless there is an explicit public requirement.
4. Create a dedicated RAM role or RAM user for the workload.
5. Grant permissions scoped only to the bucket/prefix the application needs to access.
6. Choose a public or internal/VPC endpoint based on where the workload runs.

Configuration example:

~~~yaml
aliyun:
  oss:
    region: ${ALIYUN_OSS_REGION}
    endpoint: ${ALIYUN_OSS_ENDPOINT}
    bucket: ${ALIYUN_OSS_BUCKET}
    key-prefix: invoices/
~~~

- **region** is the region where the bucket was created, e.g., **ap-southeast-1**.
- **endpoint** is the OSS endpoint corresponding to the region and network path. Workloads in the same region/VPC can use the internal endpoint where supported by the product.
- **bucket** is the bucket name, not the object key.
- **key-prefix** is an application-managed prefix used to separate object types.

SDK V2 can infer the public endpoint from the region; if using an internal endpoint, acceleration endpoint, or custom domain, configure it per SDK documentation. With SDK V1, explicitly configure the endpoint and the bucket's region when using Signature V4.

**Note for buckets in Chinese mainland:** OSS policy effective from 20/03/2025 requires new OSS users to use a custom domain/CNAME for data API operations in affected mainland regions; if using HTTPS, a valid SSL certificate must be attached. Review the policy and the list of covered operations in OSS documentation before relying on the default public endpoint.

### 3.2. Least-Privilege RAM Permissions

Common actions:

| Operation | RAM Action |
| --- | --- |
| Upload object | **oss:PutObject** |
| Download object | **oss:GetObject** |
| Delete object | **oss:DeleteObject** |
| List objects in bucket | **oss:ListObjects** or the list action matching the API/version |
| Multipart upload | **oss:PutObject** and related permissions per operation |
| Write object tags | **oss:PutObjectTagging** |
| Server-side encryption with KMS | Add required KMS permissions, e.g., **kms:GenerateDataKey** and/or **kms:Decrypt** as configured |

Do not grant **AliyunOSSFullAccess** or account-wide permissions if the application only needs to upload/download within a single prefix. Policies should restrict resources by bucket and object prefix; if the application does not need delete or list capabilities, do not grant those actions.

A role's **trust policy** defines which workload may assume the role; its permission policy defines what OSS operations the role may perform. These two policies answer two different questions. On ECS, use an instance RAM role; on ACK, consider RRSA/OIDC per ServiceAccount; for environments outside Alibaba Cloud, use federation or AssumeRole as appropriate.

## 4. Integrating OSS Java SDK V1 with Spring Boot

### 4.1. Adding Dependencies

Maven example for Spring Boot 3 and OSS Java SDK V1:

~~~xml
<properties>
    <aliyun.oss.version>3.18.4</aliyun.oss.version>
    <aliyun.credentials.version>1.0.8</aliyun.credentials.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.aliyun.oss</groupId>
        <artifactId>aliyun-sdk-oss</artifactId>
        <version>3.18.4</version>
    </dependency>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>credentials-java</artifactId>
        <version>1.0.8</version>
    </dependency>
</dependencies>
~~~

**credentials-java** supports RAM roles, ECS RAM roles, OIDC roles, and the credential provider chain. Verify version compatibility of the credentials library with the OSS SDK and current Java dependencies. Do not repeat version numbers across multiple modules; manage them centrally via Maven properties or a version catalog.

### 4.2. Configuring the OSS Client and Signature V4

The client should be created once in the Spring context and reused. Do not create a new OSSClient per request because the client manages an HTTP connection pool.

Bean example:

~~~java
package demo.storage.config;

import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.comm.SignVersion;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OssClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    public OSS ossClient(
            CredentialsProvider ossCredentialsProvider,
            @Value("${aliyun.oss.endpoint}") String endpoint,
            @Value("${aliyun.oss.region}") String region) {

        ClientBuilderConfiguration clientConfig =
                new ClientBuilderConfiguration();

        // Use Signature V4 and declare the bucket's region.
        clientConfig.setSignatureVersion(SignVersion.V4);

        return OSSClientBuilder.create()
                .endpoint(endpoint)
                .credentialsProvider(ossCredentialsProvider)
                .clientConfiguration(clientConfig)
                .region(region)
                .build();
    }
}
~~~

**destroyMethod = shutdown** releases connections when the Spring context shuts down. Keep HTTPS and default CRC data checks enabled to protect data in transit and verify integrity. Do not disable CRC solely for speed without assessing the risk.

### 4.3. Credentials for Local Development

On a developer workstation, you can use environment variables for a least-privilege test RAM user:

~~~powershell
$env:OSS_ACCESS_KEY_ID = "<RAM_USER_ACCESS_KEY_ID>"
$env:OSS_ACCESS_KEY_SECRET = "<RAM_USER_ACCESS_KEY_SECRET>"
~~~

Provider bean for the local environment (profile `local`):

~~~java
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.auth.CredentialsProviderFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
public class OssCredentialsConfiguration {

    @Bean
    public CredentialsProvider ossCredentialsProvider() {
        return CredentialsProviderFactory
                .newEnvironmentVariableCredentialsProvider();
    }
}
~~~

Never put AccessKeys in application.yml, source code, Docker images, logs, or committed files. Never use the root account's AccessKey. If using static STS credentials, refresh the token before expiration; do not leave a fixed short-lived token in a long-running application.

### 4.4. Auto-Refreshing Credentials via ECS RAM Role

When Spring Boot runs on ECS/ECI, attach an instance RAM role with minimal OSS permissions. The Credentials tool retrieves STS credentials from metadata and refreshes them automatically. Below is an alternative configuration for the local provider, using profile `ecs`:

~~~java
package demo.storage.config;

import com.aliyun.credentials.Client;
import com.aliyun.credentials.models.Config;
import com.aliyun.credentials.models.CredentialModel;
import com.aliyun.oss.common.auth.Credentials;
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.auth.DefaultCredentials;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("ecs")
public class OssRoleCredentialsConfiguration {

    @Bean
    public Client ecsCredentialsClient() throws Exception {
        Config config = new Config();
        config.setType("ecs_ram_role");
        String roleName = System.getenv("ALIBABA_CLOUD_ECS_METADATA");
        if (roleName != null && !roleName.isEmpty()) {
            config.setRoleName(roleName);
        }
        config.setDisableIMDSv1(true);
        return new Client(config);
    }

    @Bean
    public CredentialsProvider ossCredentialsProvider(
            Client ecsCredentialsClient) {
        return new CredentialsProvider() {
            @Override
            public void setCredentials(Credentials credentials) {
                // Provider fetches fresh credentials from the Credentials tool.
            }

            @Override
            public Credentials getCredentials() {
                CredentialModel credential =
                        ecsCredentialsClient.getCredential();

                return new DefaultCredentials(
                        credential.getAccessKeyId(),
                        credential.getAccessKeySecret(),
                        credential.getSecurityToken());
            }
        };
    }
}
~~~

Set **ALIBABA_CLOUD_ECS_METADATA** to the name of the instance RAM role attached to ECS. **setDisableIMDSv1(true)** enforces security-hardened metadata mode; if IMDSv2 is unavailable, the application must fail rather than silently falling back. This configuration requires that the ECS instance actually has the role attached and the metadata endpoint is reachable from the workload.

On ACK, replace the provider with **oidc_role_arn**, specifying the role ARN, OIDC provider ARN, and token file per RRSA. The Credentials tool fetches STS tokens and refreshes them automatically. For cross-account access, use **ram_role_arn** and verify that both the caller's **sts:AssumeRole** permission and the target role's trust policy allow it.

## 5. Uploading and Downloading Objects

### 5.1. Object Keys and Data

OSS stores data by **bucket + object key**. An object key may contain directory-like prefixes, such as **invoices/2026/11/order-1001.pdf**, but this is a full object name rather than a physical directory.

Do not use the raw filename uploaded by a user directly as the object key. The backend should generate an unpredictable key, verify ownership, and validate file type/size before uploading. The object key does not include the bucket name.

### 5.2. Creating the Upload Service

Example using Spring MultipartFile:

~~~java
package demo.storage;

import com.aliyun.oss.OSS;
import com.aliyun.oss.model.CannedAccessControlList;
import com.aliyun.oss.model.ObjectMetadata;
import com.aliyun.oss.model.PutObjectRequest;
import com.aliyun.oss.model.PutObjectResult;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;

@Service
public class OssStorageService {

    private final OSS ossClient;
    private final String bucketName;

    public OssStorageService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public String uploadInvoice(String objectKey, MultipartFile file)
            throws IOException {

        ObjectMetadata metadata = new ObjectMetadata();
        metadata.setContentLength(file.getSize());
        if (file.getContentType() != null) {
            metadata.setContentType(file.getContentType());
        }
        metadata.setObjectAcl(CannedAccessControlList.Private);

        PutObjectRequest request;
        try (InputStream input = file.getInputStream()) {
            request = new PutObjectRequest(bucketName, objectKey, input);
            request.setMetadata(metadata);

            PutObjectResult result = ossClient.putObject(request);
            return result.getETag();
        }
    }
}
~~~

This snippet sets the object to private and returns the ETag to store alongside the business record. Client-supplied Content-Type is not reliable proof of file type; production code must validate file contents, size, extension, upload permissions, and object key naming rules.

Do not automatically construct public URLs from bucket/object names. For private objects, the backend can stream contents through the SDK or issue a time-limited presigned URL.

### 5.3. Streaming Object Downloads

There is no need to buffer an entire large file into a byte[]. You can stream from OSS directly to an HTTP response:

~~~java
import com.aliyun.oss.OSS;
import com.aliyun.oss.model.OSSObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StreamUtils;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

@Service
public class OssDownloadService {
    private final OSS ossClient;
    private final String bucketName;

    public OssDownloadService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public void download(String objectKey, OutputStream responseBody)
            throws IOException {
        OSSObject object = ossClient.getObject(bucketName, objectKey);
        try (InputStream input = object.getObjectContent()) {
            StreamUtils.copy(input, responseBody);
        }
    }
}
~~~

Before downloading, verify that the user is authorized to view that business object. Do not let clients pass an arbitrary bucket name; the backend must resolve the bucket and object key from authenticated data.

### 5.4. Handling Metadata and Object Overwrites

An object can store metadata such as Content-Type, Content-Disposition, cache control, storage class, server-side encryption, and tags. Set metadata at upload time when known in advance.

If uploading to a key that already exists, a standard PutObject operation overwrites the content. Options include:

- Generate a unique object key for each upload.
- Enable versioning if business requirements call for retaining object history.
- Use the **x-oss-forbid-overwrite** header per supported APIs to forbid overwrites.
- Store ETag, version ID, and object key in the database for reconciliation.

Do not treat ETag as a SHA-256 checksum in all cases; multipart uploads and encryption methods can cause ETag semantics to differ from a simple content hash.

## 6. Large File Uploads, Multipart, and Resumable Uploads

### 6.1. Choosing an Upload Method

| Method | Purpose | Notes |
| --- | --- | --- |
| **Simple upload** | Small/medium files, single request | OSS Java SDK V1 supports single objects up to 5 GB |
| **Multipart upload** | Splits an object into parts, uploadable in parallel | Requires initiate, upload part, complete; can abort on failure |
| **Resumable upload** | Large files or unstable networks | Saves checkpoints and resumes from completed parts |
| **Browser form upload** | Browser uploads directly via an HTML form | Different from a presigned PUT URL |
| **Presigned PUT URL** | Client uploads directly via HTTP PUT | Backend grants temporary permission for a single object key |

OSS Java SDK V1 supports multipart/resumable uploads for large objects; documentation states a multipart limit up to **48.8 TB**. Do not use simple upload for large files when resumability or request timeout limits matter.

### 6.2. Multipart Upload Lifecycle

~~~mermaid
flowchart TD
    A["InitiateMultipartUpload"] --> B["Receive uploadId"]
    B --> C["Split file into parts"]
    C --> D["UploadPart in parallel or sequentially"]
    D --> E{"All parts and ETags ready?"}
    E -->|"Yes"| F["CompleteMultipartUpload"]
    E -->|"No / error"| G["AbortMultipartUpload"]
    F --> H["Completed object"]
~~~

Each part has a part number and an ETag. Upon completion, submit the valid list of part ETags to CompleteMultipartUpload. If the process fails, abort the upload to release incomplete parts; you can also configure lifecycle rules to clean up abandoned multipart uploads.

Increase concurrency only after measuring bandwidth, memory, connection pool capacity, and quotas. Uploading many parts in parallel can boost throughput, but it also increases open connections and memory buffers.

## 7. Granting Upload/Download Access via Presigned URLs

### 7.1. Why Use Presigned URLs?

If every byte of every file flows through Spring Boot, the backend becomes a relay bottleneck consuming bandwidth, CPU, memory, and connections. An alternative flow:

1. Client asks the backend to upload a file.
2. Backend authenticates the user, checks business rules, and generates an object key.
3. Backend uses the OSS SDK to generate a presigned URL for PUT or GET.
4. Client transfers the file directly to OSS using the issued URL and HTTP method.
5. Client reports completion; backend verifies object metadata/size and updates business state.

A signed URL grants temporary access to an object for the signed HTTP method. The URL recipient does not need to hold an Alibaba Cloud AccessKey.

### 7.2. Example Generating a Download URL

~~~java
import com.aliyun.oss.OSS;
import com.aliyun.oss.HttpMethod;
import com.aliyun.oss.model.GeneratePresignedUrlRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URL;
import java.util.Date;

@Service
public class OssPresignedUrlService {
    private final OSS ossClient;
    private final String bucketName;

    public OssPresignedUrlService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public URL createDownloadUrl(String objectKey) {
        Date expiresAt = new Date(System.currentTimeMillis() + 10 * 60 * 1000);

        GeneratePresignedUrlRequest request =
                new GeneratePresignedUrlRequest(bucketName, objectKey);
        request.setMethod(HttpMethod.GET);
        request.setExpiration(expiresAt);

        return ossClient.generatePresignedUrl(request);
    }
}
~~~

This example creates a URL expiring in 10 minutes. With Signature V4, the maximum expiration for a presigned URL is 7 days; if the source credential is an STS token, the URL stops working once the credential expires. In production, use short TTLs matching your needs rather than multi-day defaults for sensitive files.

### 7.3. Example Generating an Upload URL

For PUT URLs, the backend must decide the object key and upload authorization. While a URL remains valid, it can be used multiple times; subsequent requests to the same key may overwrite the object. Therefore:

- Generate randomized keys tied to the user and upload session.
- Set a short TTL.
- Constrain the HTTP method and headers where possible.
- After upload, the backend verifies object existence, size, metadata, and scan status.
- Never accept an arbitrary object key or bucket sent by the client.
- Never treat a presigned URL as a business authentication mechanism; it only grants temporary access to an object.

When uploading directly from a browser, configure CORS for the exact allowed origins, methods, and headers. Avoid wildcard origins/methods without a clear justification.

## 8. Securing Object Storage

### 8.1. Private Buckets and Sensitive Data

- Keep buckets and objects private by default.
- Grant **oss:GetObject** only to workloads that need to read; never enable public-read for convenience.
- Use short-TTL presigned URLs for temporary file sharing.
- Validate file type, size, malware scanning, and ownership before processing.
- Never use client-supplied filenames directly as keys.
- Consider server-side encryption with KMS, versioning, and lifecycle rules per retention requirements.
- Never log full presigned URLs because the signed URL acts as a bearer credential until it expires.

### 8.2. Permissions by Workload

| Workload | Recommended Permissions |
| --- | --- |
| Invoice uploader | **oss:PutObject** within the invoices prefix |
| Invoice reader | **oss:GetObject** within the invoices prefix |
| Cleanup worker | **oss:ListObjects** and **oss:DeleteObject** within the cleanup prefix |
| Presigned GET URL API | **oss:GetObject** on objects permitted for sharing |
| Presigned PUT URL API | **oss:PutObject** on backend-generated keys |

Do not grant delete permissions to an uploader unless necessary. If a service only writes files, it does not need to list the entire bucket. Use RAM roles/STS to shorten credential lifetimes and avoid storing long-lived AccessKeys in containers.

### 8.3. Server-Side Encryption and Lifecycle

If SSE-KMS is enabled, the workload needs corresponding KMS permissions in addition to OSS permissions. When using encryption, verify key policies, region alignment, and KMS invocation permissions. Lifecycle rules can transition storage classes or expire objects; configure lifecycle rules to comply with invoice retention and legal archiving requirements.

## 9. Error Diagnosis and Retries

### 9.1. Distinguishing Client Errors from Server Errors

OSS Java SDK V1 typically distinguishes:

- **ClientException**: client/network-side errors, such as DNS, timeouts, TLS, or failure to send the request.
- **OSSException**: the request reached OSS and was rejected by the server; contains an error code, message, and request ID.

Common errors:

| Error | Cause | Resolution |
| --- | --- | --- |
| **AccessDenied** | RAM role/user lacks action or resource permission | Check principal, policy, and bucket/object prefix |
| **SignatureDoesNotMatch** | Wrong AccessKey/STS, missing token, endpoint/region/signature mismatch, or clock skew | Check credential provider, region, endpoint, and Signature V4 |
| **NoSuchBucket** | Wrong bucket name or bucket does not exist in that region | Confirm bucket name and region |
| **NoSuchKey** | Wrong object key or object does not yet exist | Verify the key stored in the DB |
| **InvalidAccessKeyId** | Wrong or disabled AccessKey, or provider picked the wrong source | Check credential source and RAM user status |
| **RequestTimeTooSkewed** | System clock drift | Synchronize NTP/time service |
| **InvalidEndpoint** or DNS error | Wrong product/region in endpoint or unreachable network path | Check official endpoint, DNS, and routing |
| **ClientException timeout** | Slow link, VPC route/firewall, or timeout too short | Inspect network, timeouts, and connection pool |
| **InvalidDigest** | Part data does not match checksum | Check stream, part ETag, and CRC/MD5 |

When catching OSSException, log errorCode, requestId, and operation details. When catching ClientException, log the message and network error type. Never log AccessKeys, SecurityTokens, or presigned URLs.

### 9.2. Retrying the Right Errors

- Apply bounded retries for timeouts, transient network errors, and eligible 5xx errors.
- Use exponential backoff with jitter to avoid synchronized retry storms across workers.
- Do not blindly retry AccessDenied, SignatureDoesNotMatch, NoSuchBucket, or NoSuchKey without fixing configuration/data first.
- For uploads to the same key, a timeout does not prove the object was not created; check HeadObject/metadata or use idempotent object keys.
- For multipart uploads, persist the upload ID and part state; abort the upload when the operation is canceled or times out.

The SDK includes built-in retries. Do not stack multiple unbounded retry layers (HTTP client + SDK + application worker) as this causes duplicate requests and prolongs failure windows.

## 10. OSS Integration Testing

### 10.1. Layered Testing

| Test Type | Objective | How to Execute |
| --- | --- | --- |
| Domain unit test | Object naming, authorization, and metadata logic | Mock the ObjectStorage interface |
| Adapter unit test | Request mapping, bucket, key, metadata | Mock the OSS client via wrapper or inspect constructed requests |
| Spring context test | OSS bean and credentials provider creation | Use a test profile and mock properties |
| Integration test | Upload/download against an OSS test bucket | Restricted RAM role/user, dedicated bucket |
| Permission test | Role has only granted permissions | Test upload/download/delete against a permission matrix |
| Presigned URL test | GET/PUT URLs work within TTL | Verify method, expiry, and object key |
| Failure test | Wrong endpoint, expired token, timeout | Verify exception classification and retry behavior |

Do not use unit tests to prove RAM policies work in the cloud. Integration tests need a dedicated bucket, test-prefixed object keys, and non-sensitive data.

### 10.2. Minimum Test Suite

1. Upload a small file and save its ETag/object key to the DB.
2. Stream-download the file and compare contents.
3. Generate a presigned GET URL with a 10-minute TTL and test access before and after expiration.
4. Grant a role only oss:PutObject and verify GET is denied.
5. Test a wrong-region bucket and wrong endpoint to inspect error codes.
6. Upload a large file via multipart/resumable upload, then simulate a network failure.
7. Confirm private objects cannot be accessed without credentials or a presigned URL.
8. Verify logs contain no AccessKeys, STS tokens, or signed URLs.

## 11. OSS Starter: When to Keep and When to Replace?

### 11.1. Using the Starter in Existing Applications

If a legacy Spring Boot application already uses **aliyun-oss-spring-boot-starter**:

1. Verify the artifact and BOM version in the effective POM.
2. Identify which beans, properties, and OSS SDK V1 version the starter creates/uses.
3. Check whether its auto-configuration can accept the required RAM role/STS provider.
4. Run context tests, upload/download integration tests, and permission tests.
5. Keep the starter if it is compatible, tested, and meaningfully reduces configuration code.

Do not add the starter alongside SDK V1 in a way that instantiates two OSS clients or duplicate property sets. If you need a new API not exposed by the starter, you can create a separate adapter/client after checking for dependency conflicts.

### 11.2. When to Switch to the Direct SDK?

Consider switching to the direct SDK when:

- The starter lacks clear compatibility documentation for your Spring Boot/JDK version.
- The starter pulls in an outdated SDK or lacks Signature V4.
- You need RAM role/STS/OIDC providers that the starter does not support cleanly.
- You need multipart, resumable uploads, presigned URLs, rich metadata, or newer APIs.
- You want explicit control over client lifecycle, timeouts, retries, and SDK versions.
- You need to upgrade to Boot 3/4 while the starter only has verified evidence on Boot 2.

When replacing the starter, define an internal **ObjectStorage** interface, write an SDK-backed adapter, run integration tests, and migrate call sites gradually. Do not swap an entire module at once without baseline tests.

### 11.3. Evaluating OSS Java SDK V2

OSS Java SDK V2 has a different API from V1 and is marked **preview** in official documentation. The available dependency on Maven Central is **com.aliyun:alibabacloud-oss-v2:0.6.1** at the time of inspection. Per documentation, SDK V2 supports Java 8+ and offers sync/async clients, retries, and extensive object operations.

If choosing V2:

- Read the release notes and preview limitations for the exact version.
- Verify that the needed APIs have samples and stable behavior.
- Create an adapter isolating the SDK from the domain.
- Test upload/download, endpoints, credentials, multipart, retries, and close lifecycle.
- Pin the version, check CVEs/transitive dependencies, and maintain a rollback path to a V1 adapter.

Do not treat version 0.6.1 as a GA commitment. Choosing a preview library must be approved under your project's release policy.

## 12. Hands-on Exercise

**Exercise:** Build an InvoiceStorageAdapter in Spring Boot to store and download PDF invoices from OSS.

1. Create a private bucket in a test region and identify the corresponding endpoint.
2. Create a RAM role for the application with only **oss:PutObject** and **oss:GetObject** under the **invoices/** prefix.
3. Configure OSS Java SDK V1 with Signature V4 and a RAM role/STS credential provider.
4. Create a singleton OSS bean that shuts down cleanly when the Spring context stops.
5. Write an ObjectStorage interface and an adapter implemented with the OSS SDK.
6. Upload a PDF, set Content-Type and private ACL, and store the ETag/object key in the database.
7. Implement streaming download and an endpoint generating short-TTL presigned GET URLs.
8. Test permission denial, wrong endpoint, expired tokens, and network timeouts.
9. Try multipart/resumable upload for a large file.
10. Compare SDK V1, SDK V2 preview, and starter 1.0.0 across API surface, compatibility, credentials, and upgradability.

**Review Questions:**

1. When should you use the OSS Java SDK directly instead of the Aliyun OSS Starter?
2. Why must starter 1.0.0 be tested separately when upgrading an application to Spring Boot 3/4?
3. Why does Signature V4 require the bucket's region?
4. Why should the OSS client be a singleton Spring bean?
5. How does a RAM role differ from a static AccessKey in credential lifecycle?
6. When should you use simple upload, multipart/resumable upload, and presigned URLs?
7. Why should object keys be generated by the backend instead of using raw filenames from clients?
8. A presigned URL is a time-limited bearer credential; what restrictions must be applied?
9. How does OSSException differ from ClientException?
10. Why does an upload timeout not necessarily prove the object was not created?
11. Why shouldn't a bucket/object be made public just for download convenience?
12. Under what circumstances is adopting the OSS SDK V2 preview acceptable in a project?

## 13. References

- [OSS SDK quick start](https://www.alibabacloud.com/help/en/oss/user-guide/oss-sdk-quick-start): configuring region, credentials, and upload/download with Java SDK V2.
- [OSS Java SDK V1](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-java-sdk/): dependencies, client, credentials provider, Signature V4, and exception handling.
- [OSS Java SDK V2](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-sdk-for-java-2-0/): SDK V2 preview, sync/async clients, credentials, endpoints, and samples.
- [Alibaba OSS SDK V2 GitHub](https://github.com/aliyun/alibabacloud-oss-java-sdk-v2): source, samples, and changelog.
- [Alibaba OSS SDK V1 GitHub](https://github.com/aliyun/aliyun-oss-java-sdk): source and OSS Java SDK V1 documentation.
- [Aliyun Spring Boot Starters](https://github.com/alibaba/aliyun-spring-boot): BOM, OSS starter, and samples.
- [Maven Central — aliyun-oss-spring-boot-starter](https://central.sonatype.com/artifact/com.alibaba.cloud/aliyun-oss-spring-boot-starter): starter version and transitive POM.
- [Alibaba Cloud Credentials for Java](https://github.com/aliyun/credentials-java): RAM roles, ECS roles, OIDC, STS, and the default credential chain.
- [OSS multipart upload for Java](https://www.alibabacloud.com/help/en/oss/developer-reference/java-multipart-upload): initiate, upload part, complete, and abort.
- [OSS upload files with Java SDK](https://www.alibabacloud.com/help/en/oss/developer-reference/overview-13/): simple, multipart, resumable, and signed URL uploads.
- [OSS presigned URL download](https://www.alibabacloud.com/help/en/oss/developer-reference/download-using-a-presigned-url): GET URLs, oss:GetObject permission, and expiration limits.
- [OSS Signature V1 to V4 migration](https://www.alibabacloud.com/help/en/oss/developer-reference/guidelines-for-upgrading-v1-signatures-to-v4-signatures): Signature V1 deprecation roadmap and how to adopt V4.

**Expected Outcome:** Learners can integrate OSS into Spring Boot using the appropriate SDK, properly configure region/endpoint and Signature V4, use RAM roles/STS instead of hardcoded AccessKeys, upload/download objects securely, issue time-limited presigned URLs, and evaluate starters based on verified compatibility evidence.

# Amazon S3: Generating presigned URLs and time-limited access

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, learners integrate Spring Boot with managed services across AWS, Azure, and Google Cloud while practicing identity authentication, authorization, secret management, and integration testing. When an application stores images, invoices, or uploaded files in **Amazon S3**, the straightforward approach is for the backend to read/write data and relay bytes to the client. However, the backend can become a bottleneck when many users transfer large files concurrently.

A **presigned URL** allows a client to send an HTTP request directly to an S3 object using pre-signed permissions within a defined time window. The Spring Boot application still checks **who is permitted to access which object** before generating the URL, while S3 handles the actual data transfer.

After this lesson, you will be able to:

1. Explain how an S3 presigned URL works, why the bucket can remain private, and where the URL's permissions come from.
2. Use **AWS SDK for Java v2** in Spring Boot to generate presigned **GET** and **PUT** URLs.
3. Choose appropriate signature durations, understand S3 Signature V4's 7-day cap, and account for **temporary credentials**.
4. Constrain bucket, object key, HTTP method, and signed headers; distinguish signature constraints from business-data validation.
5. Protect upload/download flows with IAM, bucket policies, CORS, user authorization checks, and monitoring.
6. Test scenarios including expired URLs, expired credentials, mismatched headers, wrong Region, and URL leakage.

> This lesson uses **Spring Cloud AWS** with **AWS SDK for Java v2** (`software.amazon.awssdk` namespace). Choose a Spring Cloud AWS version compatible with your project's actual Spring Boot version. Code snippets use illustrative bucket names; do not point at production data during practice.

## 1. Why use presigned URLs?

Suppose a user wants to download an 80 MiB PDF invoice. There are two ways to route the data:

| Access pattern | Data path | Spring Boot's responsibility |
| --- | --- | --- |
| Backend as proxy | Browser → Spring Boot → S3 (or reverse) | Authenticate, authorize, open stream, and relay every byte |
| Presigned URL | Browser ↔ S3 directly | Authenticate, authorize, issue scoped time-limited URL, track state |

With a presigned URL, the backend does not hold a long-lived read/write connection to S3 for every large file; yet the backend remains responsible for **authorization, quotas, object locking/keys, auditing, and business state**.

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Spring Boot API
    participant DB as Business database
    participant S3 as Private S3 bucket

    U->>API: GET /documents/42/download-url
    API->>DB: Check owner/tenant and fetch object key
    DB-->>API: Authorized + corresponding key
    API-->>U: Presigned GET URL (10 min)
    U->>S3: GET directly using URL
    S3-->>U: Object content
~~~

A presigned URL **does not turn ACLs or bucket policies public**. The bucket can keep **S3 Block Public Access** enabled and use `Bucket owner enforced` Object Ownership. Access is authenticated via the **signature bound to the IAM principal** that generated the URL, within that principal's effective permissions.

### 1.1. What does a presigned URL contain?

Illustrative structure of a Signature Version 4 URL:

~~~text
https://training-private-docs.s3.ap-southeast-1.amazonaws.com/
    documents/invoice-42.pdf
    ?X-Amz-Algorithm=AWS4-HMAC-SHA256
    &X-Amz-Credential=...%2F20261124%2Fap-southeast-1%2Fs3%2Faws4_request
    &X-Amz-Date=20261124T090000Z
    &X-Amz-Expires=600
    &X-Amz-SignedHeaders=host
    &X-Amz-Signature=<signature>
    [&X-Amz-Security-Token=...]
~~~

Line breaks are added purely for readability; the real URL is a **single string**. Key parameters:

- `X-Amz-Algorithm`: signing algorithm, typically `AWS4-HMAC-SHA256`.
- `X-Amz-Credential`: identifies the signing credential and date/Region/service scope. This is **not** the secret access key.
- `X-Amz-Date`: signing timestamp; combined with `X-Amz-Expires` to define the signature's maximum validity window.
- `X-Amz-Expires`: signature duration in **seconds**.
- `X-Amz-SignedHeaders`: set of HTTP headers included in the signature; the client must send matching values.
- `X-Amz-Signature`: signature computed from the canonicalized request and signing key.
- `X-Amz-Security-Token`: present when the signer uses **temporary credentials**; this token is part of the signed request.

The example is **mocked** and cannot be used to access any object. The signature binds the request to **HTTP method, host/bucket, key, query parameters, and signed headers**. Changing GET to PUT, altering the key, or modifying a required header normally causes S3 to reject the request as an invalid signature.

**Do not treat the URL as public information.** Anyone holding an unexpired presigned URL can generally perform the signed action during its validity period; the URL acts like a *bearer capability* and does not require the recipient to log into an AWS account.

## 2. How is a presigned URL's lifetime actually determined?

A common mistake is thinking `signatureDuration(Duration.ofHours(1))` guarantees the URL works for one full hour regardless of anything else. Actual validity depends on **multiple simultaneous limits**:

1. **Signature validity window:** `X-Amz-Date` and `X-Amz-Expires`; for S3 presigned URLs signed with AWS Signature V4, the maximum supported duration is **7 days**.
2. **Credential expiration:** if the signer uses an IAM role/STS/temporary credentials, the URL stops working once those credentials expire, even if `X-Amz-Expires` is still long.
3. **IAM policies, bucket policies, and additional constraints:** an explicit deny, `s3:signatureAge` limits, network conditions, or KMS permissions can deny the request earlier.
4. **Resource state:** the object may be deleted, replaced by another version, moved, or blocked by policy; the URL does not guarantee the object remains present.

~~~text
Signing time: 09:00
SignatureDuration: 60 minutes     → signature expires at latest 10:00
Role credentials expire: 09:30
Bucket policy signatureAge: 10 minutes → requests after 09:10 are denied

=> URL is only usable within the window satisfying ALL THREE.
   IAM, KMS, and object state must also remain valid.
~~~

The expiration **is not a timer for S3 to auto-delete the object**. Expiration only causes requests using the old URL to be rejected; data remains stored and managed by versioning, lifecycle rules, and retention policies.

### 2.1. Can a GET/PUT URL be reused?

Yes. While still valid, a presigned GET URL can be opened multiple times. A presigned PUT URL can also be re-submitted, and a PUT to the **same object key** can overwrite the current data or create a new version if versioning is enabled.

Thus, a presigned URL is **not a single-use token by default**. If business rules allow only one upload, add controls such as generating a dedicated random key per upload session, tracking `PENDING_UPLOAD → READY` state, validating before issuing URLs, signing conditional writes where supported, and refusing/stopping link issuance once complete.

### 2.2. Can a URL be revoked immediately?

There is no simple `revoke URL by ID` operation for an arbitrary S3 presigned URL. Options depend on the use case:

- Use a **short TTL** from the moment of creation, such as 5–15 minutes.
- Add a bucket policy rejecting overly old signatures via `s3:signatureAge`.
- Change permissions or add an explicit deny, replace/remove the object, or invalidate credentials when appropriate; note that such changes may impact other requests.
- For business flows requiring exact real-time revocation per user/session, have the backend authorize each request and **stream through the API**, or use a dedicated controlled distribution mechanism.

Merely deleting the link record from your database **does not immediately deactivate an already-issued URL**; S3 verifies the signature and policies directly and does not query your application database.

## 3. Preparing Spring Boot, S3Presigner, and IAM

### 3.1. Dependencies

Import the Spring Cloud AWS BOM with a version compatible with your Spring Boot version and add the S3 starter:

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

`spring-cloud-aws.version` is a Maven property that must be declared according to your project's compatibility matrix. `spring-cloud-aws-starter-s3` integrates S3 configuration and the AWS SDK into Spring Boot; the examples use **`S3Presigner`** from AWS SDK v2.

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
    presigned:
      get-minutes: 10
      put-minutes: 5
~~~

`app.storage.*` are application-defined properties, **not** built-in properties of the S3 starter. The Region must match the bucket's Region. The durations are only examples; production systems should pick values based on file size, network conditions, policy, and risk.

### 3.2. Signing identity

In AWS, use an **IAM role attached to the workload** (ECS task role, instance profile, or appropriate EKS identity). Development machines can use an AWS CLI profile/SSO and temporary credentials. The AWS SDK uses the **Default Credentials Provider Chain** unless overridden.

`S3Presigner` uses the credentials of the signing principal. That principal must hold permissions for the signed action, such as `s3:GetObject` or `s3:PutObject`, on the target object. The fact that Spring Boot succeeds in generating a URL does not mean S3 will accept it if the principal lacks permission when the request executes.

**Never store access keys/secret keys in source code, YAML, or responses.** Responses should contain only the URL to use, expiration info, and any headers the recipient must send.

### 3.3. `S3Presigner` bean for a Spring application

Depending on your Spring Cloud AWS version and configuration, `S3Presigner` may be auto-configured. If your project does not already have this bean, you can declare the bean below. `@ConditionalOnMissingBean` prevents creating a duplicate bean if one already exists:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration(proxyBeanMethods = false)
public class S3PresignerConfiguration {

    @Bean
    @ConditionalOnMissingBean(S3Presigner.class)
    public S3Presigner s3Presigner(
            @Value("${spring.cloud.aws.region.static}") String region) {
        return S3Presigner.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

If the starter already provides `S3Presigner`, simply inject that bean without adding extra configuration.

In test environments using an S3-compatible emulator, the presigner must also match the **endpoint, addressing style, Region, and credentials** used by the client. Updating the endpoint only on `S3Client` while forgetting `S3Presigner` causes URLs to be signed for a different host and fail.

### 3.4. IAM policy restricting object keys

Example where the backend role can only read published documents and upload into the `incoming/` area:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPublishedDocuments",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::training-private-docs/documents/*"
    },
    {
      "Sid": "UploadIncomingFiles",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::training-private-docs/incoming/*"
    }
  ]
}
~~~

This is an illustrative **identity-based policy** and does not by itself cover bucket policies, permission boundaries, SCPs, or KMS key policies. `s3:GetObject` and `s3:PutObject` bind to **object ARNs**, while LIST permissions (if needed) bind to the **bucket ARN**. Grant only the permissions the application actually needs; a backend issuing GET URLs does not need DELETE permission.

The backend's IAM role may be able to access all of `documents/*`, yet user A is **not automatically** permitted to read user B's documents. Business authorization must be verified before every URL issuance.

## 4. Generating presigned GET URLs with AWS SDK v2

### 4.1. Service issuing URLs for pre-authorized keys

The following example assumes the API layer has verified the user may view the document and passes a **trustedKey** retrieved from the database:

~~~java
import java.time.Duration;
import java.time.Instant;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PresignedGetObjectRequest;

@Service
public class S3DownloadUrlService {
    private final S3Presigner presigner;
    private final String bucket;

    public S3DownloadUrlService(
            S3Presigner presigner,
            @Value("${app.storage.bucket}") String bucket) {
        this.presigner = presigner;
        this.bucket = bucket;
    }

    public record DownloadGrant(String url, Instant expiresAt) {}

    public DownloadGrant presignDownload(String trustedKey) {
        if (trustedKey == null
                || !trustedKey.startsWith("documents/")) {
            throw new IllegalArgumentException("Invalid object key");
        }

        GetObjectRequest get = GetObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build();

        GetObjectPresignRequest request = GetObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(10))
                .getObjectRequest(get)
                .build();

        PresignedGetObjectRequest signed =
                presigner.presignGetObject(request);

        return new DownloadGrant(
                signed.url().toExternalForm(),
                signed.expiration());
    }
}
~~~

`presignGetObject` **computes the signature and URL**; generating the URL itself does not download the file from S3. The object might not exist or might be denied when the recipient uses the URL. `signed.expiration()` reflects the signature's expiration time; **temporary credentials or policies** can cause the URL to stop working sooner.

If you want the browser to download the file with a custom display filename, S3 GET supports override parameters such as `responseContentDisposition` when constructing `GetObjectRequest`. Use only sanitized filenames to prevent header injection and misleading content.

### 4.2. Connecting to business authorization

A secure endpoint accepts a **document ID** rather than an arbitrary S3 key:

~~~java
// API layer integration example; DocumentRecord and
// DocumentAuthorizationService are project business classes.
@GetMapping("/api/documents/{documentId}/download-url")
public S3DownloadUrlService.DownloadGrant issueDownloadLink(
        @PathVariable java.util.UUID documentId,
        org.springframework.security.core.Authentication user) {

    DocumentRecord record =
            documentAuthorizationService.requireCanRead(
                    user, documentId);

    return s3DownloadUrlService.presignDownload(record.objectKey());
}
~~~

**Sequence to preserve:** authenticate user → look up `documentId` → check owner/tenant/business permissions → fetch key from stored data → sign URL. If a controller merely accepts `?key=documents/tenants/other-user/...`, a user can probe another user's keys and turn the backend's broad role into a cross-tenant read vector.

For sensitive documents, keep lifetimes short, rate-limit link generation, and log **document ID, user ID, action, and request ID**. Do not log the full URL because its query string contains the signature and session token.

### 4.3. Using the GET URL on the client

~~~bash
# Use the URL intact, including all query parameters.
curl --fail --location --output invoice.pdf "$PRESIGNED_GET_URL"
~~~

The URL is signed for an exact path/key and query string; do not alter the host, Region, object name, or `X-Amz-*` parameters. In browsers, simply navigate to the URL or invoke `fetch` with GET. If making a cross-origin `fetch` where JavaScript reads the response, S3 CORS configuration must allow the corresponding origin and method.

A presigned GET URL works for a single valid GET request to that object; it is **not** a URL for listing the bucket or accessing all keys under the same prefix.

## 5. Generating presigned PUT URLs for direct client uploads

### 5.1. Secure upload model

The backend creates a **new server-controlled key** for each upload session. The client receives only the URL and agreed-upon HTTP headers:

~~~mermaid
sequenceDiagram
    actor U as Client
    participant API as Spring Boot API
    participant DB as Business database
    participant S3 as Private S3 bucket

    U->>API: POST /uploads/init (file type, size)
    API->>API: Authentication, quota, check file type
    API->>DB: Create PENDING_UPLOAD + random key
    API-->>U: Presigned PUT URL (5 min), key, Content-Type
    U->>S3: PUT object directly with signed headers
    S3-->>U: HTTP 200 + ETag
    U->>API: POST /uploads/{id}/complete
    API->>S3: HEAD key + verify metadata/size
    API->>DB: READY if valid; handle discrepancies
~~~

**Never mark a file READY simply because a URL was issued.** The client can abandon the upload, lose connectivity, or upload content different from what it declared. The backend should re-verify the object and bind it to the stored upload session.

### 5.2. Service signing PUT URLs

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

@Service
public class S3UploadUrlService {
    private static final Set<String> ALLOWED_TYPES = Set.of(
            "application/pdf", "image/png", "image/jpeg");

    private final S3Presigner presigner;
    private final String bucket;

    public S3UploadUrlService(
            S3Presigner presigner,
            @Value("${app.storage.bucket}") String bucket) {
        this.presigner = presigner;
        this.bucket = bucket;
    }

    public record UploadGrant(
            String objectKey,
            String url,
            Instant expiresAt,
            String contentType) {}

    public UploadGrant presignUpload(
            String trustedTenantId, String validatedContentType) {

        // Tenant ID must come from trusted authentication data.
        if (trustedTenantId == null
                || !trustedTenantId.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid Tenant ID");
        }
        if (!ALLOWED_TYPES.contains(validatedContentType)) {
            throw new IllegalArgumentException(
                    "Unsupported upload format");
        }

        // Do not use the client's originalFilename as the object key.
        String key = "incoming/" + trustedTenantId + "/"
                + UUID.randomUUID();

        PutObjectRequest put = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(validatedContentType)
                .build();

        PutObjectPresignRequest request =
                PutObjectPresignRequest.builder()
                        .signatureDuration(Duration.ofMinutes(5))
                        .putObjectRequest(put)
                        .build();

        PresignedPutObjectRequest signed =
                presigner.presignPutObject(request);

        return new UploadGrant(
                key,
                signed.url().toExternalForm(),
                signed.expiration(),
                validatedContentType);
    }
}
~~~

Checking `Content-Type` against an allowlist **does not inspect the actual file bytes**: a client can still upload data different from the declared type. After upload, the backend must enforce size limits, inspect actual format, or scan the file as required; for systems handling external files, keep new uploads in a **quarantine/pending** state until validated.

`signed.httpRequest().headers()` can be inspected to see which headers are included in the presigned HTTP request. Signed headers must be sent accordingly by the client; in particular, if `Content-Type` is part of the signature, the client must send that exact value. Do not arbitrarily alter `x-amz-*` or other signed headers.

### 5.3. Sending PUT with curl

~~~bash
# URL must be quoted because the query string contains & characters.
curl --fail --request PUT \
  --header "Content-Type: image/png" \
  --upload-file "./photo.png" \
  "$PRESIGNED_PUT_URL"
~~~

The command above is valid only when the URL was signed for **`Content-Type: image/png`** (or signed without conflicting constraints). If the presigner signed additional headers, the client must send those exact headers as well. For browsers, the API should return the information needed for JavaScript to set the allowed headers, paired with matching CORS configuration.

**A presigned PUT does not reliably enforce file size on its own** just because the API earlier accepted a `fileSize` parameter. To enforce strict upload size, consider a **presigned POST policy with a `content-length-range` condition** when appropriate, route uploads through a size-bounded backend/proxy, or verify actual size post-upload and delete/quarantine quota-exceeding objects. Each option carries different scope and trade-offs.

### 5.4. Does a PUT URL prevent overwrites?

Not by default. If an unexpired PUT URL is re-submitted to the **same bucket/key**, the request can overwrite current content or create a new version in a versioning-enabled bucket. Using a fresh random key per upload session prevents cross-session collisions, yet **does not block replaying the same URL**.

For a `create-only` policy, S3 can support **conditional writes** with the `If-None-Match: *` header on PUT when supported by the API/SDK and bucket mode. If using this condition, the header must be properly included in the request and signature, and the client must send that header. Do not treat `HEAD followed by PUT` as race-condition protection, because another request can write the object in between.

If business logic requires processing a file only once, create a unique upload session and enforce state/idempotency in the database, regardless of how many times the S3 URL is invoked.

## 6. Time-limiting access with a bucket policy

When the application issues links, `signatureDuration` is the first layer. For critical data, you can add a **server-side S3 limit** so overly old signed URLs are rejected even if the application accidentally issued a longer expiration.

### 6.1. Restricting signature age with `s3:signatureAge`

The bucket policy below denies presigned GET/PUT URLs using query-string authentication when the signature age exceeds **600,000 milliseconds (10 minutes)**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyStalePresignedObjectRequests",
      "Effect": "Deny",
      "Principal": "*",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::training-private-docs/*",
      "Condition": {
        "StringEquals": {
          "s3:authType": "REST-QUERY-STRING"
        },
        "NumericGreaterThan": {
          "s3:signatureAge": "600000"
        }
      }
    }
  ]
}
~~~

Meaning:

- `s3:signatureAge` is the **signature age in milliseconds**; do not confuse it with `X-Amz-Expires` in seconds.
- `s3:authType = REST-QUERY-STRING` targets query-string authentication—typically presigned URLs—rather than requests signed in HTTP headers.
- `Effect: Deny` is an **explicit deny**, so it blocks requests even when an IAM identity policy allows them.
- The policy **does not grant** GET/PUT permissions. The IAM principal still needs appropriate allow permissions.
- The resource in this example covers objects in the illustrative bucket. In real applications, narrow actions/prefixes and test thoroughly to avoid breaking legitimate workflows.

For example, if the app issues a 30-minute GET URL while the policy denies signatures older than 10 minutes, the effective TTL is shortened. Conversely, if the app issues only a 5-minute URL, a 10-minute bucket policy **does not extend** the URL's validity to 10 minutes.

### 6.2. Other access conditions

In certain architectures you might also consider:

- **Network restrictions** such as `aws:SourceIp` or `aws:SourceVpce` in policies, if the network path permits. For mobile users, IP addresses can change between receiving and using a link.
- **KMS key policies** for buckets using SSE-KMS; a signing role with S3 permissions but missing required KMS permissions will still fail.
- **Explicit deny** against public access or requests failing encryption requirements.
- **Credentials rotation/session timeout** acting as an indirect bound on temporary credentials.

Specifically, if a bucket policy requires `aws:SourceVpce` for all operations, browsers on the public Internet generally **do not traverse your AWS VPC endpoint**, so presigned URLs will be blocked even with a valid signature. Align the data path with network policies—for instance, using a backend/proxy inside the VPC or an appropriately authorized distribution layer.

### 6.3. Why not use public ACLs?

Making a bucket or object public so a user can download a file grants overly broad access that is hard to control. Presigned URLs let a user perform a signed action for a specific period while keeping the bucket private. In modern S3 setups, `Bucket owner enforced` Object Ownership disables ACLs altogether; avoid building designs around toggling per-object ACLs unnecessarily.

## 7. CORS and header errors when uploading from browsers

Accessing S3 directly from a web page is **cross-origin** when the frontend domain differs from the S3 host. Browsers enforce **Cross-Origin Resource Sharing (CORS)**, especially for PUT requests or requests with custom headers.

Example CORS configuration for a test bucket:

~~~json
[
  {
    "AllowedOrigins": [
      "https://app.example.test"
    ],
    "AllowedMethods": [
      "GET",
      "PUT",
      "HEAD"
    ],
    "AllowedHeaders": [
      "Content-Type",
      "x-amz-*"
    ],
    "ExposeHeaders": [
      "ETag"
    ],
    "MaxAgeSeconds": 300
  }
]
~~~

**CORS is not an IAM policy.** A request allowed by the browser under CORS still requires a valid signature and must satisfy IAM/bucket policies. Conversely, a properly signed URL may work via `curl` while failing in a browser due to missing `AllowedOrigins`, `AllowedMethods`, or required headers.

- Add only controlled origins; avoid broad wildcards when environment isolation is required.
- Browser PUT uploads usually trigger a **preflight OPTIONS** request; S3 evaluates CORS against the bucket configuration.
- If JavaScript needs to read the response `ETag` to send to a completion/multipart endpoint, configure `ExposeHeaders` accordingly.
- When the client sends headers that differ from the signed headers (for example, `Content-Type` is altered or a required `x-amz-*` header is added/omitted), S3 can return `SignatureDoesNotMatch`.
- Browsers manage certain headers like `Host` automatically; do not instruct the frontend to manually set forbidden headers. Inspect the actual signed headers required by the presigner.

In many systems, GET only needs browser navigation to the URL; CORS becomes critical when JavaScript reads the response directly via `fetch` or uploads via PUT from the browser.

## 8. Completion checks, quotas, and data protection

Presigned URLs solve the problem of **delegating a single HTTP request**; they do not replace the full file management lifecycle.

### 8.1. Upload state model

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Uploading: Issue presigned URL
    Uploading --> Verifying: Client reports completion
    Verifying --> Ready: Size/format/permission checks pass
    Verifying --> Rejected: Invalid data
    Pending --> Expired: Timed out without completion
    Uploading --> Expired: No confirmation within deadline
    Rejected --> Cleaned: Clean up object
    Expired --> Cleaned: Clean up unconfirmed object
    Ready --> [*]
~~~

One way to manage state in the application:

1. **Initiate:** authenticate user, check preliminary quota, generate a unique random key, create a `PENDING` record with a business `uploadId`.
2. **Sign:** issue a short-lived PUT URL restricted to the chosen bucket/key and expected headers.
3. **Client uploads:** client uploads directly to S3, then submits the business `uploadId` to notify completion.
4. **Verify:** backend checks user/tenant ownership, calls `HeadObject` to verify size and metadata, and if required inspects actual bytes or scans content before marking `READY`.
5. **Expire/cleanup:** clean up stale pending objects and records; handle cases where the user abandons the upload without notifying the backend.

**Note:** `HeadObject.contentType()` reflects only recorded metadata; it does not prove the actual bytes are PDF/PNG/JPEG. Content scanning and size bounds must match your application's security and cost requirements. Avoid exposing newly uploaded objects publicly or to other users before verification completes.

### 8.2. Large file uploads: presigned multipart

A single presigned PUT URL suits small/medium files that fit in one request. For large files, use **S3 multipart upload**:

1. The backend authenticates the user and calls `CreateMultipartUpload` to obtain an S3 `uploadId`.
2. The backend issues presigned `UploadPart` URLs bound to **partNumber + uploadId + key**.
3. The client uploads each part directly to S3 and captures the returned `ETag` for every part.
4. The client asks the backend to complete; the backend checks permissions, validates parts, and calls `CompleteMultipartUpload`.
5. If the user cancels or the upload remains incomplete, the backend calls `AbortMultipartUpload` and configures an S3 Lifecycle rule to clean up incomplete uploads.

~~~mermaid
flowchart LR
    B["Browser: split file into parts"] -->|"Request URL for parts 1..N"| A["Spring Boot API"]
    A -->|"Presign each UploadPart"| B
    B -->|"Direct PUT"| S["Private S3 bucket"]
    B -->|"partNumber + ETag"| A
    A -->|"Complete after verification"| S
~~~

Multipart parts have specific rules (minimum 5 MiB except the last part, part-count limit, and ascending order during Complete). Permission checks and expiration windows for each presigned part URL must still be controlled. **Never let a client pass another user's `uploadId`/key for the backend to call Complete** without verifying session ownership.

### 8.3. Sensitive data in URLs and logs

Presigned URLs embed **signatures and sometimes session tokens** in the query string. To reduce exposure risk:

- Deliver URLs only over HTTPS and only to application-authenticated users.
- Do not write full URLs to access logs, analytics, traces, frontend error reports, support tickets, or chat alerts.
- Do not embed URLs on pages or third-party resources that might leak them via `Referer`; consider `Referrer-Policy` and appropriate cache headers.
- Do not allow the frontend to forward presigned URLs to unauthorized third-party services for inspection or URL "shortening".
- Never embed tokens, secrets, or sensitive personal data in object keys or user metadata.
- Rate-limit link issuance and monitor anomalies (excessive link requests, multiple IPs, repeated upload failures).

Expiration limits the exposure window if a URL leaks, but never replaces authorization before issuing the URL.

## 9. Presigned URL error handling and testing

### 9.1. Common errors table

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `SignatureDoesNotMatch` | Method, host, path, query, or signed header differs from signed request | Inspect intact URL, Content-Type, endpoint, URL encoding |
| `AccessDenied` (403) | IAM/bucket policy/KMS, signatureAge, expired credentials | Review signer permissions, explicit deny, KMS, and timestamps |
| `Request has expired` / expiration errors | `X-Amz-Expires` elapsed or signatureAge policy blocked it | Check signing timestamp, TTL, and system clock |
| Clock skew or future-dated signature error | Large clock drift on signer/client, wrong signing date | Synchronize system clocks, SDK signer/Region |
| Browser reports CORS error while curl succeeds | S3 CORS missing origin/method/header | Check preflight OPTIONS and bucket CORS config |
| GET returns 404/403 | Key does not exist or access denied | Cross-check key in database; HEAD with authorized role if needed |
| PUT succeeded but backend still sees non-READY | Client did not call complete or backend has not verified yet | Check PENDING state, HEAD object, business retry |
| URL expires earlier than expected | IAM role credentials expired, bucket policy denied early | Check session credentials and `s3:signatureAge` |
| URL points to wrong host or Region | Presigner and bucket Region differ, mismatched custom endpoint | Inspect `S3Presigner` bean, Region, bucket endpoint |
| Upload exceeds quota | PUT URL does not enforce business quota itself | Use POST policy or verify/clean up data post-upload |

**403 does not have a single root cause.** When an object does not exist, S3 returns 404 if the caller has `s3:ListBucket`, or 403 if lacking that permission. Never use a single HTTP status code to infer definitively whether an object exists.

### 9.2. Integration testing in an AWS sandbox

Testing can be split into three layers:

- **Unit tests:** mock `S3Presigner` and the authorization service to verify the system signs only authorized keys, caps TTLs, sets the right GET/PUT method, and issues no URL when the user is denied.
- **Integration tests with an emulator:** verify URL signing, PUT/GET, Content-Type, CORS, and endpoints when supported by the emulator. Emulators do not necessarily model IAM, KMS, `signatureAge`, or STS lifetimes accurately.
- **AWS sandbox:** test a private bucket, real IAM role, `s3:signatureAge` policy, temporary credentials, SSE-KMS if applicable, browser CORS, and expiration cases.

Suggested test scenarios:

1. Issue a short-TTL presigned GET URL for a test object the caller is allowed to read; verify HTTP GET succeeds and bytes match.
2. Call GET with a URL whose **key**, method, or query was modified; verify S3 rejects the signature.
3. Issue a presigned PUT URL with an agreed `Content-Type`; test PUT with matching header and then PUT with a mismatched header.
4. In a controlled sandbox, use a short TTL to verify requests after expiration are rejected—no need to wait hours in a learning environment.
5. Verify a `s3:signatureAge` policy blocks URLs older than the threshold even when `signatureDuration` is longer.
6. Test user A requesting user B's document: **the API must refuse to issue a URL** to user A.
7. Test a case where PUT succeeds but the client never reports completion; the record stays pending and gets cleaned up.
8. Test browser GET/PUT from an allowed origin and a disallowed origin; compare against `curl` to separate CORS errors from signature errors.
9. Confirm logs never contain `X-Amz-Signature` or `X-Amz-Security-Token` query parameters.

Perform deletion, credential-expiry, or policy-deny tests only on dedicated test buckets/roles. In production, rely on controlled pre-release test results and runtime observability rather than intentionally breaking live credentials or policies.

### 9.3. Acceptance criteria for the feature

A presigned URL feature is ready for further review when:

- Every URL issuance is tied to a verified user/tenant and authorized document/upload ID.
- TTLs are configured, capped on the backend, and never exceed credential/policy bounds.
- Method, key, `Content-Type`, and signed headers are consistently enforced between API and client.
- The bucket remains private; the IAM role can access only the required prefixes/operations.
- Uploads include post-completion verification and cleanup of stale pending states.
- CORS allows only required origins; full signed URLs are never logged.
- Tests cover expired URLs, replayed PUTs, authorization failures, header mismatches, and real browser execution.

## 10. Comparison with Azure and Google Cloud

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module also covers managed services from Azure and Google Cloud. The concept of granting temporary client access is similar, though signature creation, permission conditions, and lifetimes differ:

| Concept | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Temporary access link | Presigned URL | **Shared Access Signature (SAS)** | **Signed URL** |
| Typical Java SDK | `S3Presigner` (AWS SDK v2) | Azure Storage Blob SDK, SAS API | GCS Storage Java client, URL signing |
| Backend identity | IAM role / SDK credentials | Managed identity / Azure Identity and appropriate SAS signing rights | Service account / signing credentials |
| Common scope | Method, bucket/key, headers, TTL | Resource, permissions, time window, optional stored policy | HTTP method, bucket/object, TTL, signed headers |
| Limits/permissions | IAM + bucket policy + signatureAge + STS | SAS permissions + time + resource/account/network settings | Google Cloud IAM + signature + provider limits/conditions |
| Browser CORS | S3 bucket CORS | Blob service CORS | Cloud Storage bucket CORS |

Do not write a multi-cloud function assuming all providers accept identical query formats or share the same day limits. A business interface can abstract this as:

~~~java
public interface TemporaryObjectAccessPort {
    TemporaryLink createDownloadLink(
            String trustedObjectId, java.time.Duration ttl);

    TemporaryLink createUploadLink(
            String uploadSessionId, java.time.Duration ttl);
}

public record TemporaryLink(
        String url,
        java.time.Instant expiresAt,
        java.util.Map<String, String> requiredHeaders) {}
~~~

The AWS adapter uses `S3Presigner`; the Azure adapter generates an appropriate SAS; the GCP adapter uses Cloud Storage signed URLs. **Authorization and session/tenant management** belong in the shared business layer, while signature limits, headers, IAM/RBAC, and maximum TTLs are handled inside each provider adapter.

## 11. Practice and review questions

### Exercise 1 — Time-limited download

Create a private sandbox bucket and a sample PDF object. Build a Spring Boot endpoint that accepts `documentId`, authenticates the user, and generates a 60-second presigned GET URL. Use `curl` to download the file before and after expiration, observing HTTP status codes. Explain why the file still exists on S3 after the URL expires.

### Exercise 2 — Direct browser upload

Create a `POST /uploads/init` endpoint issuing a 5-minute presigned PUT URL for a UUID key under `incoming/`. Write a test page using JavaScript `fetch` to PUT a PNG. Configure S3 CORS for a fixed local origin and `ExposeHeaders: ETag`. After upload, have the backend call HEAD and transition the upload status to READY.

### Exercise 3 — Headers and signatures

Generate a PUT URL bound to `Content-Type: image/png`. Try sending the matching Content-Type, a different Content-Type, and a different HTTP method. Record the S3 responses and compare against the exact set of headers signed by the presigner.

### Exercise 4 — IAM and signature age limits

In a sandbox bucket, configure a role with only GET on `documents/*` and PUT on `incoming/*`. Try signing GET for an out-of-scope key, then test the URL. Apply a 60-second `signatureAge` bucket policy on a test prefix, generate a 10-minute URL, and verify it is rejected once past the policy threshold.

### Exercise 5 — Threat modeling

Analyze these scenarios: URL leaked in logs; user passes another tenant's key; client replays the same PUT URL; uploaded object exceeds quota; temporary credentials expire early; browser CORS request is rejected. For each scenario, identify the appropriate control layer: application, IAM/bucket policy, S3 API, CORS, or monitoring.

### Self-check questions

1. Does a presigned URL make a bucket or object public?
2. Why can someone without an AWS account still use a valid presigned GET URL?
3. Which parts of an HTTP request are bound by the signature?
4. How does `X-Amz-Expires` differ from the lifetime of STS credentials?
5. What unit does `s3:signatureAge` use, and how can it shorten effective TTL?
6. Why is a PUT URL not single-use by default?
7. Why is a controller that accepts a raw object key from the client and signs a URL dangerous?
8. Why must the backend inspect the object after the client reports upload completion?
9. When is a presigned POST policy more convenient than a presigned PUT for size enforcement?
10. Why can `curl` succeed while a browser reports a CORS error?
11. Which fields in the URL and response must never be written to logs?
12. If per-user access must be revoked immediately, why is an already-issued long-TTL GET URL a disadvantage?
13. In a temporary-link API across AWS, Azure, and GCP, which logic should stay shared and which belongs in adapters?

By the end of this lesson, learners should be able to issue presigned **GET/PUT** URLs from Spring Boot, bound duration and permission scope, properly verify upload/download flows, protect private data, and evaluate risks when applying signed-URL patterns across cloud providers.

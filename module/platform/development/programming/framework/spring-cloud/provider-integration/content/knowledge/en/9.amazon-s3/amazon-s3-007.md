# Amazon S3: Encryption, versioning, and object lifecycle

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot applications integrate with managed services from AWS, Azure, and Google Cloud to handle storage, messaging, data, secret management, identities, and permissions. For **Amazon S3**, successfully storing an object is only the first step: the system must also know **which key encrypts the object**, **whether previous versions can be recovered after accidental overwrites or deletions**, and **how soon data transitions between storage classes or expires**.

This lesson focuses on three mechanisms:

1. **Encryption:** protecting content in transit and at rest, distinguishing SSE-S3, SSE-KMS, DSSE-KMS, SSE-C, and client-side encryption.
2. **Versioning:** retaining versions of the same object key, understanding version IDs, delete markers, restoration, and version deletion.
3. **Lifecycle:** automatically transitioning storage classes, expiring objects, managing noncurrent versions, and cleaning up incomplete multipart uploads.

By the end of this lesson, you will be able to configure Spring Boot + Spring Cloud AWS to PUT objects with SSE-KMS, inspect encryption/version metadata, design controlled lifecycle policies, explain IAM/KMS permissions, and test recovery on an AWS sandbox.

> **Scope:** Examples use AWS SDK for Java v2 (`software.amazon.awssdk` packages) and modern Spring Cloud AWS (`io.awspring.cloud` namespace). Choose versions compatible with your Spring Boot version. Buckets, objects, and KMS ARNs in this document are purely illustrative.

## 1. Three mechanisms solving three different problems

An S3 object is identified by **bucket + key**, plus a **version ID** if the bucket has Versioning enabled. Encryption applies to data bytes, Versioning manages history, and Lifecycle acts on data over time.

~~~mermaid
flowchart TD
    API["Spring Boot API"] -->|"HTTPS, AWS SDK + IAM role"| S3["Private S3 bucket"]
    KMS["SSE-S3 / AWS KMS key"] -->|"Encrypt data at rest"| S3
    S3 --> V1["reports/a.pdf · version v1"]
    S3 --> V2["reports/a.pdf · version v2"]
    S3 --> DM["reports/a.pdf · delete marker v3"]
    LIFE["Lifecycle rules"] -->|"Transition/expiration"| V1
    LIFE -->|"Transition/expiration"| V2
    LOCK["Object Lock/retention (if used)"] -->|"Restrict version deletion"| V1
~~~

| Requirement | Primary mechanism | Limitation |
| --- | --- | --- |
| Protect bytes in transit | HTTPS/TLS | TLS does not replace encryption at rest |
| Encryption at rest | SSE-S3, SSE-KMS, DSSE-KMS, or client-side encryption | Encryption does not retain history when an object is deleted |
| Recover older versions | S3 Versioning | Does not automatically prevent edits from stale data or permanent version deletion |
| Transition/delete by age | S3 Lifecycle | Does not guarantee second-level timing; does not replace legal retention |
| Keep versions non-deletable for a period | Object Lock/retention/legal hold | Requires dedicated policies and configuration |
| Decide who can read/write | IAM, bucket policy, KMS policy, and business authorization | No encryption mechanism checks document ownership on its own |

For example: an invoicing system requires **private buckets, SSE-KMS, Versioning, a noncurrent retention policy, and ownership checks**. Those components complement each other; no single mechanism covers security, history, and lifecycle on its own.

## 2. Encryption in transit and at rest

### 2.1. Encryption in transit

Spring Boot applications use **HTTPS/TLS** when calling S3. Browsers downloading files via presigned URLs should also use HTTPS; presigned URLs carry signatures and sometimes session tokens, so avoid exposing them in logs or error messages.

TLS protects the transport channel between endpoints. Once bytes are written by S3 to storage, **server-side encryption** protects content at rest. These two layers complement each other.

### 2.2. Encryption at rest: comparison table

| Mode | Who manages keys | When to use | Key notes |
| --- | --- | --- | --- |
| **SSE-S3** | S3 manages server-side encryption keys | Standard encryption-at-rest needs | Applied automatically by S3 to new objects by default |
| **SSE-KMS** | AWS KMS key managed by AWS or customer | Need key policies, auditing, and fine-grained key-usage control | Both S3 and KMS permissions may be required |
| **DSSE-KMS** | Two layers of server-side encryption integrated with KMS | Stricter compliance/control requirements | Verify feature support, KMS permissions, and cost |
| **SSE-C** | Caller supplies encryption key to S3 on relevant requests | Special cases with custom key-management workflows | Client must store the key safely to decrypt later |
| **Client-side encryption** | Application encrypts before transfer | Must protect bytes before data leaves the application | Key management, algorithms, and decryption/recovery live in the application |

Since 2023, S3 automatically applies server-side encryption using **SSE-S3 (AES-256)** to new objects unless another mode is specified. Therefore, **omitting an SSE-KMS request header** does not mean new data is stored as plaintext. However, security or compliance policies may mandate customer-managed KMS keys.

**SSE-KMS does not mean data is encrypted inside Spring Boot before upload.** S3 performs encryption server-side; if encryption must occur before bytes leave the application, you must implement client-side encryption separately.

### 2.3. SSE-KMS and key usage permissions

When using SSE-KMS, a PUT/GET request must pass through multiple layers:

~~~mermaid
flowchart LR
    APP["Spring Boot IAM role"] --> IAM["S3 identity/bucket policy"]
    IAM --> S3["S3 PutObject / GetObject"]
    S3 --> KMS["KMS key policy + IAM/grant"]
    KMS --> RESULT["Encryption / decryption permitted"]
~~~

Typically required permissions:

- **PUT with SSE-KMS:** `s3:PutObject` and `kms:GenerateDataKey` on the corresponding KMS key.
- **GET SSE-KMS:** `s3:GetObject` and `kms:Decrypt` when decryption is needed.
- **Multipart upload, CopyObject, or certain checksum modes:** may also require `kms:Decrypt`/`kms:GenerateDataKey` depending on the operation and settings.
- **KMS key policy:** when using a customer-managed KMS key, the key policy or a grant must allow the principal to use the key; an IAM allow alone may not suffice.

The key used for SSE-KMS must match the bucket's **Region**. If a KMS key is disabled, scheduled for deletion, or its policy is modified, stored objects can become unreadable even though the object versions remain.

**S3 Bucket Keys** can reduce KMS requests and costs with SSE-KMS under supported conditions, though they change how S3 uses encryption context. If your project has policies depending on encryption context, verify compatibility before enabling Bucket Keys.

### 2.4. When to choose SSE-S3, SSE-KMS, or client-side encryption?

- Choose **SSE-S3** when the primary requirement is standard encryption at rest with minimal operational overhead.
- Choose **SSE-KMS with a customer-managed key** when you need key policies, control over which principals use the key, auditing, or specific compliance controls.
- Choose **DSSE-KMS** only when explicitly required and after verifying cost, permissions, and support boundaries.
- Choose **client-side encryption** if data must be encrypted **before leaving the application boundary**; requires an independent key-management and recovery process.
- Choose **SSE-C** only in specialized setups designed to safeguard keys reliably; losing the key renders data undecryptable.

Never put secrets, raw encryption keys, session tokens, or sensitive data into user metadata, object keys, or logs.

## 3. Integrating Spring Boot with SSE-KMS

### 3.1. Dependencies and configuration

The Spring Cloud AWS S3 starter configures the AWS SDK v2 `S3Client` for injection into Spring services. With Maven:

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

`spring-cloud-aws.version` must be declared according to the compatibility matrix for your actual Spring Boot version; no single version fits every project.

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
    kms-key-arn: ${S3_KMS_KEY_ARN}
~~~

`app.storage.*` are **application-chosen property names**. Never hard-code access keys/secret keys: the AWS SDK uses the default credentials provider chain (AWS profile/SSO locally, IAM role or workload identity in deployment).

### 3.2. Illustrative identity policy

Example role authorized to read/write documents and use a test KMS key:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteDocuments",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::training-private-files/documents/*"
    },
    {
      "Sid": "UseDocumentEncryptionKey",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/EXAMPLE-KEY-ID"
    }
  ]
}
~~~

Replace the bucket, account, and key ARN with your sandbox values. With a **customer-managed KMS key**, the key policy/grant must also allow these actions. The role above has **no** bucket administration permissions such as `s3:PutBucketVersioning`, `s3:PutLifecycleConfiguration`, or permanent version deletion `s3:DeleteObjectVersion`; separate those operational permissions from the upload/download API.

### 3.3. Uploading with SSE-KMS via `S3Client`

~~~java
import java.io.InputStream;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;
import software.amazon.awssdk.services.s3.model.ServerSideEncryption;

@Service
public class EncryptedDocumentStorage {
    private final S3Client s3;
    private final String bucket;
    private final String kmsKeyArn;

    public EncryptedDocumentStorage(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket,
            @Value("${app.storage.kms-key-arn}") String kmsKeyArn) {
        this.s3 = s3;
        this.bucket = bucket;
        this.kmsKeyArn = kmsKeyArn;
    }

    public record StoredObject(
            String key, String versionId, String eTag) {}

    public StoredObject upload(
            InputStream source, long exactLength,
            String verifiedContentType) {

        if (exactLength < 0) {
            throw new IllegalArgumentException("Invalid length");
        }

        String key = "documents/" + UUID.randomUUID();

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(verifiedContentType)
                .serverSideEncryption(ServerSideEncryption.AWS_KMS)
                .ssekmsKeyId(kmsKeyArn)
                .build();

        PutObjectResponse response = s3.putObject(
                request,
                RequestBody.fromInputStream(source, exactLength));

        return new StoredObject(
                key,
                response.versionId(),
                response.eTag());
    }
}
~~~

Key details illustrated by this snippet:

1. **The key is backend-generated**; clients cannot specify arbitrary keys. The mapping user/tenant → documentId → key must be persisted in the database after permission checks.
2. `serverSideEncryption(AWS_KMS)` requests SSE-KMS, and `ssekmsKeyId` selects the key.
3. `RequestBody.fromInputStream` requires the **exact byte count**. The caller must keep the stream open throughout PUT and close it afterward.
4. `response.versionId()` is useful when S3 returns a version ID. For buckets without versioning enabled, do not assume a version ID is generated like in an enabled bucket.
5. `ETag` is not always the content MD5 (especially with multipart/encryption). Use supported checksums when byte integrity verification is required.

For large files, use streaming/multipart upload or presigned URLs as appropriate; avoid `getBytes()` loading entire files into RAM.

### 3.4. Reading encryption metadata with HEAD

~~~java
var info = s3.headObject(b -> b
        .bucket(bucket)
        .key("documents/example.pdf"));

System.out.println("Encryption: " + info.serverSideEncryptionAsString());
System.out.println("KMS key: " + info.ssekmsKeyId());
System.out.println("Version ID: " + info.versionId());
System.out.println("Content-Type: " + info.contentType());
~~~

`HeadObject` reads metadata without downloading the body, though it is still a network request. For normal SSE-S3/SSE-KMS objects, **do not send the `x-amz-server-side-encryption` request header on GET/HEAD**; that encryption request header belongs to PUT/write operations.

### 3.5. Bucket default encryption and key rotation

Another operational approach is configuring **default bucket encryption** via IaC/admin (for example, SSE-KMS with an organization key). PUT requests then do not have to specify the mode on every call, provided the bucket policy and permissions align.

Keep in mind:

- Changing bucket default encryption only governs **subsequent writes**; existing objects are **not automatically** re-encrypted with the new key.
- To migrate already-stored objects to a new key configuration, run a copy/rewrite or appropriate batch process and verify completion.
- If a bucket policy requires requests to include an **explicit SSE-KMS header**, PUTs omitting that header can still be **Denied**, even when bucket default encryption is set to SSE-KMS. Do not confuse `header present` with `final object encrypted`.
- For copy/multipart operations, verify decrypt permissions on the source key and data-key generation permissions on the destination KMS key.

## 4. S3 Versioning: three states and semantics

### 4.1. Unversioned, Enabled, Suspended

| State | Behavior on PUT to same key | Behavior on standard DELETE by key |
| --- | --- | --- |
| **Unversioned** (never enabled) | Current object is replaced | Object is deleted |
| **Enabled** | Creates a new version ID; old versions remain | Inserts a **delete marker**, hiding the current object |
| **Suspended** | Follows specific rules around **null versions**, stops generating new version IDs like Enabled | Has special behavior with null versions/delete markers |

Once Versioning is enabled on a bucket, it can be **suspended**, yet it never reverts completely to an unversioned bucket. Existing versions remain unless explicitly deleted or removed by lifecycle rules.

### 4.2. Timeline of an object

~~~text
T0 PUT documents/a.pdf  → version v1 (current)
T1 PUT documents/a.pdf  → version v2 (current), older v1
T2 DELETE key           → delete marker v3 (current)

GET key                  → usually no current object visible
GET key, versionId=v1    → old v1 content, if authorized
GET key, versionId=v2    → v2 content, if authorized
DELETE versionId=v3      → deletes marker, v2 can become current again
DELETE versionId=v1      → permanently deletes version v1
~~~

~~~mermaid
flowchart LR
    A["PUT v1"] --> B["v1: old data"]
    C["PUT v2"] --> D["v2: new data"]
    E["DELETE key"] --> F["v3: delete marker"]
    F -->|"Default GET key"| G["Current object not visible"]
    B -->|"GET versionId=v1"| H["Readable v1 if authorized"]
    D -->|"GET versionId=v2"| I["Readable v2 if authorized"]
~~~

**A delete marker does not contain object content.** It hides the key's current view. Versions v1/v2 continue occupying storage and incurring costs. By contrast, **DELETE with a version ID** permanently deletes that specific version, requires separate permissions, and may be unrecoverable without backups/replicas.

### 4.3. Enabling versioning on a sandbox bucket

~~~bash
aws s3api put-bucket-versioning \
  --bucket training-private-files \
  --versioning-configuration Status=Enabled

aws s3api get-bucket-versioning \
  --bucket training-private-files
~~~

These illustrative commands are only for a **dedicated sandbox** and require permissions such as `s3:PutBucketVersioning`. Do not toggle versioning automatically on every Spring Boot instance startup. After enabling versioning for the first time, verify its status has stabilized before running sensitive write/delete operations.

### 4.4. How do Version ID and ETag differ?

| Attribute | Purpose | Do not assume |
| --- | --- | --- |
| `versionId` | Identifies a specific version in a versioned bucket | Not a sequence number or timestamp |
| `ETag` | References object state / If-Match precondition | Not always MD5, and not equivalent to version ID |
| `Last-Modified` | Storage/modification timestamp info | Does not guarantee optimistic locking |
| `Checksum` | Byte integrity verification | Does not replace application authorization |

**Versioning does not prevent lost updates on its own.** Two people editing version A can sequentially PUT B and C, making C current even though B remains in history. To prevent logical overwrites, use conditional PUT (`If-Match`) or database optimistic locking, and consider immutable keys per revision.

## 5. Reading and restoring versions in AWS SDK v2

### 5.1. Listing versions and delete markers

`ListObjectsV2` mainly lists current objects. To inspect history, use **`ListObjectVersions`**:

~~~java
import software.amazon.awssdk.services.s3.model.ListObjectVersionsRequest;

String key = "documents/example.pdf";

var response = s3.listObjectVersions(
        ListObjectVersionsRequest.builder()
                .bucket(bucket)
                .prefix(key)
                .build());

response.versions().stream()
        .filter(v -> key.equals(v.key()))
        .forEach(v -> System.out.println(
                "version=" + v.versionId()
                + " latest=" + v.isLatest()
                + " eTag=" + v.eTag()));

response.deleteMarkers().stream()
        .filter(m -> key.equals(m.key()))
        .forEach(m -> System.out.println(
                "marker=" + m.versionId()
                + " latest=" + m.isLatest()));
~~~

This returns **one page** of results. If an object has many versions, iterate pages using the `keyMarker`/`versionIdMarker` pair or a supported paginator; do not assume the first page holds the full history.

Relevant permissions:

- `s3:ListBucketVersions` on the **bucket ARN** when listing versions.
- `s3:GetObjectVersion` on the **object ARN** when GETting a specific version.
- `s3:DeleteObjectVersion` on the **object ARN** when deleting a specific version.
- `s3:GetObject` and `s3:DeleteObject` are separate permissions for standard current-object operations.

### 5.2. Downloading an older version by version ID

~~~java
import java.io.IOException;
import java.io.OutputStream;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public void downloadVersion(
        S3Client s3,
        String bucket,
        String authorizedKey,
        String trustedVersionId,
        OutputStream target) throws IOException {

    // Business layer has already verified documentId, owner/tenant, and version.
    var request = GetObjectRequest.builder()
            .bucket(bucket)
            .key(authorizedKey)
            .versionId(trustedVersionId)
            .build();

    try (var input = s3.getObject(request)) {
        input.transferTo(target);
    }
}
~~~

With SSE-KMS buckets, appropriate KMS permissions are also needed. Never allow users to pass another user's key/version ID arbitrarily even when the backend IAM role could GET it.

### 5.3. Restoring an older version

You can **delete the current delete marker** so the previous version reappears, though deleting a marker alters history and requires version-deletion permissions. An audit-friendly alternative is **creating a new version from the older version's content**, preserving prior history.

Illustrative example for a small file:

~~~java
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

var oldContent = s3.getObjectAsBytes(
        GetObjectRequest.builder()
                .bucket(bucket)
                .key("documents/example.txt")
                .versionId(approvedOldVersionId)
                .build());

var result = s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key("documents/example.txt")
                .contentType("text/plain; charset=UTF-8")
                .build(),
        RequestBody.fromBytes(oldContent.asByteArray()));

System.out.println("New version ID = " + result.versionId());
~~~

Loading the entire content into RAM is **only for small files**. For large files, use streaming/copy mechanisms; preserve metadata, tags, `Content-Type`, and SSE-KMS settings as required. To avoid overwriting another concurrent edit, use conditional writes/optimistic locking instead of an unconditional PUT.

## 6. What actions does S3 Lifecycle manage?

**S3 Lifecycle** lets you define bucket rules so the service evaluates object/version age and transitions storage classes, expires objects, or cleans up abandoned uploads.

| Action | Target resource | Result |
| --- | --- | --- |
| **Transition** | Current object | Moves to another storage class once eligible |
| **Expiration** | Current object | In versioned buckets typically adds a delete marker; in unversioned buckets deletes the object |
| **NoncurrentVersionTransition** | Noncurrent versions | Transitions older versions to another storage class |
| **NoncurrentVersionExpiration** | Noncurrent versions | Deletes older versions when eligible; may remove restoration capability |
| **AbortIncompleteMultipartUpload** | Uncompleted multipart uploads | Cleans up abandoned parts, reducing cost |
| **ExpiredObjectDeleteMarker** | Delete markers with no remaining versions | Cleans up markers per service conditions when no other versions exist |

Lifecycle filters can use **prefixes**, tags, or supported condition combinations. Do not confuse Lifecycle with a Java job deleting at exact second precision; S3 processes rules asynchronously.

### 6.1. Storage classes: cost and restore time

| Storage class | When to use | What to consider |
| --- | --- | --- |
| **S3 Standard** | Frequent access | Storage pricing tailored to active access |
| **S3 Standard-IA** | Infrequent access requiring fast retrieval | Retrieval fees and minimum storage duration |
| **S3 One Zone-IA** | Reproducible data or single-AZ tolerance | Unsuitable for sole copies needing multi-AZ durability |
| **S3 Intelligent-Tiering** | Unpredictable access patterns | Monitoring/tiering fees per pricing rules |
| **S3 Glacier Instant Retrieval** | Infrequently accessed archives needing millisecond reads | Retrieval fees and minimum duration |
| **S3 Glacier Flexible Retrieval** | Archives that can wait for restore | Requires a restore workflow before reading |
| **S3 Glacier Deep Archive** | Long-term archival, rarely read | Restore time and tier pricing |

Transitioning **does not always save money for small objects** due to minimum duration charges, transition request fees, and minimum billable object sizes. Base choices on retention duration, recoverability, read cost, and data classification.

### 6.2. Lifecycle is not an exact deletion clock

A rule like `Expiration after 7 days` marks when an object becomes **eligible** to expire under S3's age calculation; it does not mean S3 promises to delete it on the exact millisecond of day 7. Therefore:

- Do not use lifecycle rules to enforce exact per-user/session link expirations.
- If the API must block reads immediately, enforce permissions/timeframes at the business layer.
- New rules can apply to **already existing** eligible objects, not only future uploads.
- With Versioning, distinguish **current expiration** from **noncurrent expiration** before finalizing rules.

## 7. Example Lifecycle policy in a sandbox

Suppose a bucket has:

~~~text
incoming/      # Unverified uploaded files
documents/     # Approved business files
reports/       # Reports infrequently accessed after initial period
~~~

Illustrative JSON configuration for AWS CLI `put-bucket-lifecycle-configuration`:

~~~json
{
  "Rules": [
    {
      "ID": "AbortIncompleteIncoming",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "incoming/"
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    },
    {
      "ID": "ExpireTemporaryIncoming",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "incoming/"
      },
      "Expiration": {
        "Days": 14
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      }
    },
    {
      "ID": "MoveOldReportsToIA",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "reports/"
      },
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "STANDARD_IA"
        }
      ],
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 365
      }
    }
  ]
}
~~~

**Meaning:**

- Multipart uploads under `incoming/` not completed within 7 days can be aborted.
- Current objects under `incoming/` become eligible for expiration after 14 days; their noncurrent versions are evaluated for deletion after `NoncurrentDays = 30`.
- Current objects under `reports/` can transition to Standard-IA after 90 days; noncurrent versions are retained up to the 365-day rule.
- `documents/` has no expiration rule in this example to avoid accidentally deleting essential business documents.

**This is not a policy to drop straight into production.** Lifecycle rules can affect existing data under matching prefixes. Inventory your data, verify legal retention windows, quotas, and noncurrent version counts, and test on a sandbox bucket first.

### 7.1. Current Expiration with Versioning

Example in a Versioning-enabled bucket:

~~~text
PUT documents/a.pdf  → v1
PUT documents/a.pdf  → v2 (current)
Lifecycle Expiration eligible
                     → delete marker (current)

v1 and v2 may remain stored as noncurrent versions.
~~~

To actually purge historical bytes, you need **NoncurrentVersionExpiration** or explicit version deletion. In unversioned buckets, Expiration deletes the current object. In **Suspended** state, null-version/delete-marker behavior must be checked separately.

### 7.2. Incomplete multipart uploads

Multipart uploads go through `CreateMultipartUpload → UploadPart → CompleteMultipartUpload`; if a process dies before Complete or Abort, uploaded parts have not formed a complete object yet still incur storage charges. An `AbortIncompleteMultipartUpload` rule acts as a service-side safety net.

This **does not delete completed objects**. If the application supports multi-day resumable uploads, set the abort threshold long enough not to disrupt valid sessions.

## 8. Object Lock, retention, and legal hold

**Versioning does not mean immutable data.** A principal holding `s3:DeleteObjectVersion` can still delete versions unless prevented by Object Lock, policies, or other protections.

**S3 Object Lock** provides retention/legal hold on **specific versions** and requires appropriate bucket versioning support. Modes:

- **Governance mode:** data is protected, though principals with special permissions and specific actions can bypass retention under defined conditions.
- **Compliance mode:** protected versions cannot have their retention shortened or removed via normal administrative actions before expiration.
- **Legal hold:** retains a version until the hold is removed by an authorized principal; independent of retention dates.

Lifecycle is not a mechanism to bypass Object Lock. A version under active retention or legal hold cannot simply be deleted because a `NoncurrentVersionExpiration` rule reached its day threshold.

If data is subject to mandatory retention policies, confirm requirements with the compliance/retention team before configuring expiration. Misconfiguring noncurrent deletion can destroy required records; setting overly long retention inflates cost and blocks legitimate deletion.

## 9. Evaluating cost, recovery, and operational risk

### 9.1. Versioning increases stored data

~~~text
PUT reports/a.pdf 20 MiB → version v1
PUT reports/a.pdf 20 MiB → version v2
PUT reports/a.pdf 20 MiB → version v3

While all three versions remain, stored content can be
approximately 60 MiB (excluding overhead/specific settings).
~~~

Uploading a new version **does not store only diffs against previous versions**. Noncurrent versions can accumulate rapidly when documents are replaced frequently.

### 9.2. Encryption has its own costs and risks

- **KMS:** key charges and request usage, throughput limits, key policy management; consider S3 Bucket Keys when appropriate.
- **Key rotation/change:** does not automatically re-encrypt all existing objects under the new key.
- **Recoverability:** having a version ID is not enough if the KMS key is disabled, blocked by key policy, or decrypt permissions are revoked.
- **Data transfer:** encryption does not eliminate cross-Region or outbound data transfer charges.

### 9.3. Aligning Lifecycle with recovery objectives

When choosing retention, ask: "If a customer discovers an accidental overwrite or deletion after **45 days**, is a version still available to restore?" If `NoncurrentVersionExpiration` deletes versions after 30 days, a 45-day recovery objective **fails**.

Versioning helps recovery, yet **does not replace full backup/disaster recovery**. Consider Object Lock, replication/independent copies, minimal delete permissions, tested retention rules, and recovery plans for KMS, policy, or regional failures.

## 10. Integration testing Spring Boot with S3

### 10.1. Three testing layers

| Layer | Should verify | Limitations |
| --- | --- | --- |
| Unit tests with mocked SDK | Request carries SSE-KMS/key ARN; version ID is stored; permission check runs before GET version | Does not prove S3 encrypts or KMS policies succeed |
| S3-compatible emulator | PUT/GET/HEAD, Versioning, and delete markers if supported by emulator | KMS, Object Lock, lifecycle timing, and IAM may differ from AWS |
| AWS sandbox | Real SSE-KMS, IAM/KMS policies, versioning, lifecycle, restore, and retention | Requires dedicated test resources; lifecycle is async and incurs cost |

### 10.2. Step-by-step lab

1. Create a private sandbox bucket, enable Block Public Access, and configure default SSE-KMS with a test KMS key.
2. Using a least-privilege test IAM role, PUT an object and verify `HeadObject.serverSideEncryption` and KMS key.
3. Enable Versioning; PUT twice to the same key with different bytes, recording each PUT's `versionId`.
4. Call `ListObjectVersions` and GET each version to compare bytes.
5. DELETE the key **without specifying a version ID** in the sandbox to observe the delete marker; then restore an older version by creating a new version.
6. Attempt to read an SSE-KMS object with a principal missing `kms:Decrypt` to see the difference between S3 permissions and KMS permissions.
7. Configure a Lifecycle rule scoped solely to a test prefix; inspect its status and criteria—**do not expect immediate expiration the moment the rule is saved**.
8. Create an abandoned multipart upload and test Abort/cleanup on the test bucket; clean up all test objects/versions and resources afterward.
9. Change the bucket's default encryption, then inspect an **existing object** to confirm that changing the default does not automatically re-encrypt prior data.

### 10.3. Negative cases to examine

- IAM role has `s3:GetObject` but lacks required KMS permissions: what happens on GET SSE-KMS?
- Customer-managed KMS key is in the wrong Region, disabled, or denied by key policy: how do PUT/GET behave?
- User A supplies a version ID belonging to tenant B's document: does the Spring Boot layer block it before calling S3?
- How does Current Expiration differ from `NoncurrentVersionExpiration` after a delete marker exists?
- If Versioning is Suspended, are there null versions or special behaviors to watch for?
- Does Object Lock/legal hold protect a version from deletion during the retention window?
- When changing bucket encryption, how are older objects audited/migrated?

## 11. Comparison across Azure Blob Storage and Google Cloud Storage

When implementing the **SPRING_CLOUD_PROVIDER_INTEGRATION** module across multiple clouds, several concepts align while permissions, property names, and semantics differ.

| Need | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Default encryption at rest | SSE-S3 | Default service-side encryption | Default server-side encryption |
| Customer-managed keys | SSE-KMS + AWS KMS | Customer-managed key via Azure Key Vault/Managed HSM | CMEK via Cloud KMS |
| Object history | S3 Versioning and version ID | Blob versioning/snapshots and soft delete as configured | Object Versioning, generation |
| Lifecycle management | S3 Lifecycle | Blob lifecycle management | Cloud Storage Object Lifecycle Management |
| Retention/immutability protection | S3 Object Lock | Immutable Blob Storage/retention | Retention policies and supported lock modes |
| Workload identity | IAM role, S3/KMS policies | Managed identity and Azure RBAC/Key Vault policies | Service account, IAM, and Cloud KMS |

A domain service can define a shared contract for uploading, reading revisions, and retention policies, while each provider adapter handles **keys, version IDs/generations, roles/RBAC, encryption, and lifecycle details**:

~~~java
public interface VersionedObjectStore {
    StoredVersion upload(
            String trustedKey, java.io.InputStream source,
            long size, String contentType) throws java.io.IOException;

    void downloadVersion(
            String trustedKey, String providerVersionId,
            java.io.OutputStream target) throws java.io.IOException;
}
~~~

`StoredVersion` is a custom business type. Never allow controllers to modify lifecycle/retention arbitrarily per user HTTP request. Those are normally infrastructure configurations managed via IaC or controlled operational processes.

## 12. Practice exercises

### Exercise A — Choosing appropriate encryption

Given three data categories—reviewed public avatars, internal contracts, and records requiring per-key auditing and control—choose SSE-S3 or SSE-KMS for each. Explain S3/KMS permissions, TLS, and how the application responds if the KMS key becomes unusable.

### Exercise B — Versioning and delete markers

Upload three content versions of `documents/lab.txt` in a sandbox. List version IDs, ETags, and `isLatest`; GET each version. DELETE without a version ID, then describe the current object state, older versions, and two ways to restore.

### Exercise C — Designing Lifecycle rules

A system wants to delete unverified uploads after 14 days, retain noncurrent document versions for 180 days, and move rarely read reports to Standard-IA after 90 days. Write rules by prefix, explain current vs. noncurrent behavior, and describe how to prevent accidental deletion rules.

### Exercise D — Testing KMS permissions

Create a test principal with only `s3:GetObject`, then compare GET on SSE-S3 vs. GET on SSE-KMS in a sandbox. Identify the minimal policy/permission changes needed to read the object without over-granting permissions.

### Exercise E — Evaluating retention and recovery

A customer reports data loss after 45 days, while the system was configured with `NoncurrentVersionExpiration = 30 days`. Analyze whether an older version still exists to restore, and propose suitable retention, backups, Object Lock, or alerting.

### Exercise F — Comparing three clouds

Build a comparison table for document storage across AWS, Azure, and GCP covering default encryption, CMK/CMEK, versioning, lifecycle, and retention protection. Propose which parts belong in shared Spring Boot code vs. provider adapters/infrastructure.

### Self-check questions

1. Does default SSE-S3 for new objects replace TLS during upload?
2. How does SSE-KMS differ from SSE-S3 in permissions and key governance?
3. Why does PUT with SSE-KMS typically require `kms:GenerateDataKey` while GET requires `kms:Decrypt`?
4. Does changing bucket default encryption re-encrypt existing objects?
5. When Versioning is Enabled, what does PUT to the same key create?
6. Does a standard key DELETE when Versioning is Enabled wipe bytes of older versions?
7. How do you read a specific version, and which IAM permissions are required?
8. Why should ETag not be assumed to equal MD5 or version ID?
9. How do Current Expiration and `NoncurrentVersionExpiration` differ?
10. Can incomplete multipart uploads incur cost even when no complete object exists yet?
11. How does transitioning objects to Glacier classes affect read/restore latency?
12. How does Object Lock differ from Versioning in data-protection goals?
13. Why should Lifecycle not be used to revoke access at exact second precision?
14. For a 90-day recovery requirement, is a 30-day noncurrent retention setting adequate?
15. Which encryption, versioning, and lifecycle logic can be abstracted across AWS/Azure/GCP, and what must remain provider-specific?

**Expected outcome:** learners can build a Spring Boot service accessing Amazon S3 with appropriate encryption and least-privilege IAM/KMS permissions, understand version and delete-marker behavior, configure lifecycle rules without losing required data, test recovery workflows, and compare managed object storage architectures across cloud providers.

# Building a Document Repository with Object Storage and Temporary Access URLs

## 1. Problem Statement and Objectives

A document management application typically needs to store invoices, contracts, images, scans, and reports. Storing all file bytes inside the database bloats the database, increases backup costs, and couples file transfer streams to the application server. A common design is to store metadata and business state in the database while keeping file contents in object storage.

In this lab, you build a document repository using Spring Boot. The backend authenticates users, checks document access permissions, generates object keys, and issues signed URLs so browsers can upload or download directly:

- **Amazon S3:** presigned URLs created with `S3Presigner`.
- **Google Cloud Storage:** V4 signed URLs created with `Storage.signUrl`.
- **Azure Blob Storage:** user delegation SAS created using a Microsoft Entra identity and a user delegation key.

Each URL grants access only for a single object, a single HTTP method, and a short duration. The bucket/container remains private; clients never receive AWS access keys, Google service account keys, Azure account keys, or backend credentials.

This lesson belongs to the **Hands-on Integration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson combines those concepts into a complete business flow: document creation, upload, verification, download URL issuance, and lifecycle management.

After completing this lesson, you will be able to:

- Design a document repository that separates metadata in a database from object bytes.
- Generate opaque object keys instead of using user-supplied filenames directly as keys.
- Issue presigned GET/PUT URLs for S3.
- Issue V4 signed GET/PUT URLs for GCS.
- Issue read-only or upload user delegation SAS URLs for Azure Blob Storage.
- Configure signer identities and least-privilege IAM/RBAC permissions.
- Design upload sessions, finalization, download authorization, and document state transitions.
- Restrict URL lifetime, HTTP method, target object, and signed headers.
- Configure CORS, verify checksum/size, and handle failed uploads.
- Test expired URLs, wrong methods, mismatched headers, and cross-tenant access.

> **Version scope:** Examples use AWS SDK for Java 2.x, the Google Cloud Storage Java client, and the Azure Storage Blob SDK for Java. Use the BOM compatible with your project's Spring Boot version. Versions in the Maven examples are placeholders; do not share a single BOM across all three providers. All URLs, buckets, containers, projects, accounts, and objects in this lesson are illustrative data.

## 2. Document Repository Architecture

### 2.1. Separating metadata from bytes

The database stores data needed for search, authorization, and business state. Object storage stores the file contents.

~~~mermaid
flowchart LR
    USER["Browser / mobile client"] --> API["Spring Boot Document API"]
    API --> AUTH["Authentication + tenant authorization"]
    AUTH --> DB["Document metadata database"]
    API --> SIGN["Provider signer adapter"]
    SIGN --> S3["Amazon S3"]
    SIGN --> GCS["Google Cloud Storage"]
    SIGN --> AZ["Azure Blob Storage"]
    USER -->|"PUT / GET with temporary URL"| S3
    USER -->|"PUT / GET with temporary URL"| GCS
    USER -->|"PUT / GET with SAS URL"| AZ
    API --> VERIFY["Verify object metadata"]
    VERIFY --> DB
~~~

The backend does not proxy entire files through the API during normal upload/download flows. The backend only grants temporary access; the browser sends bytes directly to storage. This reduces Spring Boot CPU, memory, network bandwidth, and connection hold times.

### 2.2. Upload flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Spring Boot
    participant DB as Database
    participant ST as Object Storage

    U->>API: POST /api/documents
    API->>API: Authenticate + authorize tenant
    API->>API: Validate filename, type, declared size
    API->>DB: Save PENDING_UPLOAD + opaque object key
    API->>ST: Sign PUT for exact object and short TTL
    ST-->>API: Temporary upload URL
    API-->>U: documentId + URL + required headers
    U->>ST: PUT bytes with signed URL
    ST-->>U: Upload success
    U->>API: POST /api/documents/{id}/complete
    API->>ST: HEAD object / read properties
    ST-->>API: Size, checksum, ETag/generation
    API->>DB: Mark AVAILABLE
    API-->>U: Document ready
~~~

### 2.3. Download flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Spring Boot
    participant DB as Database
    participant ST as Object Storage

    U->>API: POST /api/documents/{id}/download-url
    API->>DB: Load document + tenant ownership
    API->>API: Check AVAILABLE and user permission
    API->>ST: Sign GET for exact object
    ST-->>API: Temporary download URL
    API-->>U: URL + expiry
    U->>ST: GET object with URL
    ST-->>U: Object bytes
~~~

Issuing a URL is an authorized action. Never issue a URL simply because a client knows a document ID or object key. The backend must verify the user, tenant, document state, and read permission before signing.

## 3. Data Model and Object Keys

### 3.1. Document metadata

A document table may include:

~~~sql
CREATE TABLE documents (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(100) NOT NULL,
    provider            VARCHAR(32) NOT NULL,
    bucket_name         VARCHAR(255) NOT NULL,
    object_key          VARCHAR(1024) NOT NULL,
    original_filename   VARCHAR(512) NOT NULL,
    content_type        VARCHAR(255) NOT NULL,
    expected_size       BIGINT NOT NULL,
    actual_size         BIGINT,
    checksum_sha256     VARCHAR(128),
    version_token       VARCHAR(256),
    state               VARCHAR(32) NOT NULL,
    upload_expires_at   TIMESTAMP WITH TIME ZONE,
    verified_at         TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    deleted_at          TIMESTAMP WITH TIME ZONE
);
~~~

`state` may include:

| State | Meaning |
| --- | --- |
| `PENDING_UPLOAD` | Document record created and upload session issued |
| `VERIFYING` | Verifying object after upload |
| `AVAILABLE` | Object verified and available for download |
| `REJECTED` | Object failed size, type, or checksum policy |
| `UPLOAD_EXPIRED` | Upload session expired without completing |
| `DELETE_PENDING` | Processing object deletion |
| `DELETED` | Document deleted according to business rules |

The database does not store signed URLs or SAS tokens. Store `upload_expires_at`, `verified_at`, and version tokens if needed for lifecycle control; URLs are regenerated whenever an authorized user requests them.

### 3.2. Server-generated object keys

Do not use user-submitted filenames directly as object keys. Filenames may contain `/`, control characters, unusual Unicode, `..`, or collide with other documents.

Example backend-generated key:

~~~text
tenant/tenant-opaque-42/documents/4c9d8b21-2c71-4e10-8d34-1d7e2a2c4f11
~~~

Store `original_filename` separately for display. Use a UUID or a sufficiently strong random identifier for the object key; derive the tenant segment from the authenticated identity and normalize it on the backend.

Object keys are not an authorization mechanism. The backend must still verify tenant ownership in the database before issuing URLs. Never let clients specify arbitrary buckets/containers or providers.

### 3.3. Shared domain contract

~~~java
import java.net.URI;
import java.time.Instant;
import java.util.Map;

public record UploadGrant(
        URI url,
        String method,
        Map<String, String> requiredHeaders,
        Instant expiresAt) {
}

public record DownloadGrant(
        URI url,
        String method,
        Instant expiresAt) {
}

public record StoredObjectMetadata(
        long sizeBytes,
        String contentType,
        String versionToken,
        String checksum) {
}

public interface DocumentObjectStorage {

    UploadGrant createUploadGrant(
            String bucket,
            String objectKey,
            String contentType,
            java.time.Duration ttl);

    DownloadGrant createDownloadGrant(
            String bucket,
            String objectKey,
            java.time.Duration ttl);

    StoredObjectMetadata head(
            String bucket,
            String objectKey);
}
~~~

The interface models business operations without exposing AWS `PresignedPutObjectRequest`, GCS `URL`, or Azure `BlobClient` to the service layer. Adapters can return additional required headers because each provider has its own request-signing rules.

## 4. Signed URLs Are Bearer Capabilities

Presigned URLs, signed URLs, and SAS tokens are all bearer credentials carrying access privileges. Anyone possessing a valid URL can perform the signed operation until the URL or signing credential expires or is revoked.

A URL should restrict:

- **Resource:** the exact bucket/container and object key.
- **Operation:** GET, PUT, or specific SAS permissions.
- **Time:** a short TTL appropriate for the upload/download duration.
- **Headers:** Content-Type or checksum if signed.
- **Identity:** the signing principal holds only the required permissions.
- **Distribution:** delivered over HTTPS and only to users authorized by the backend.

| What a signed URL protects | What a signed URL does not protect on its own |
| --- | --- |
| Restricts to a specific object | User's business permissions within the application |
| Restricts to the signed method/permission | Limiting the number of times the URL is used |
| Limits time window | Automatically deleting the object when the URL expires |
| Can bind specific request headers | Preventing users from sharing the URL with others |
| Uses the signer's permissions | Checking tenant ownership every time the URL is used |

URLs can be copied or saved in browser history, proxy logs, analytics, chat, or screenshots. Do not write full URLs to application logs, tracing spans, exception messages, or audit events. Do not place a signed URL inside a query parameter of another URL. Return responses containing URLs with `Cache-Control: no-store` and transmit only over HTTPS.

An expired URL does not mean the object has expired. The object remains in the bucket until the application deletes it or a lifecycle policy handles it.

## 5. Designing TTLs and Signer Permissions

### 5.1. Business-driven TTLs

A starting policy might be:

| Use case | Suggested TTL | Rationale |
| --- | ---: | --- |
| Small file upload | 5–10 minutes | Reduces window of URL exposure |
| Regular document download | 2–5 minutes | Backend can issue a new URL when the user needs it |
| Large file download | 10–30 minutes | Allows time for download and retries |
| Multipart/resumable upload | Per session/part | Each part has its own URL or session token |

These are starting baselines, not mandatory provider limits. Measure file sizes, network speeds, and retry needs when choosing TTLs. Do not use a provider's maximum allowed TTL as the application default.

### 5.2. URL lifetime depends on the signing credential

| Provider | Limits / characteristics |
| --- | --- |
| S3 | SDK/CLI supports up to 7 days with SigV4; URLs signed with temporary role credentials expire when those credentials expire, even if a longer TTL was specified |
| GCS | V4 signed URLs max out at 7 days; if signing via IAM `signBlob`, use short TTLs because signatures created with Google-managed service account keys can become invalid sooner upon key rotation |
| Azure | User delegation keys have a maximum lifetime of 7 days; SAS validity must fall within the key's lifetime and is subject to storage account policies |

An S3 URL may expire earlier than `signatureDuration` if the IAM role's session token expires or the credential is revoked. GCS signed URLs require a valid signer and `signBlob` permission; Azure user delegation SAS depends on the user delegation key and the RBAC permissions of the principal that requested the key.

The `expiresAt` field in application responses must represent the **actual effective expiration timestamp**, not merely the requested `now + ttl`. For S3, cap it at the temporary credentials' expiration; for GCS, respect the signer/key lifetime and V4 limit; for Azure, do not exceed the user delegation key's expiration. The calculations in the adapter examples use illustrative TTLs; production adapters must return an effective expiration capped by the actual credential lifetime.

### 5.3. Separating signer identity from end users

End users do not need cloud IAM identities. The backend authorizes the user and uses its workload identity to sign URLs. Users receive a scoped capability, not the signer's access token.

The signer should only have:

- Object read permission if issuing download URLs.
- Object creation permission if issuing upload URLs.
- URL signing permission corresponding to the provider's mechanism.
- No bucket administration, IAM, or data deletion permissions unless needed.

Never use Owner/Administrator accounts to sign URLs in production.

## 6. Amazon S3 — Presigned URLs with AWS SDK for Java 2.x

### 6.1. IAM permissions

The signer needs permissions matching the requests it signs:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDocuments",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::training-document-vault/documents/*"
    },
    {
      "Sid": "UploadDocuments",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::training-document-vault/documents/*"
    }
  ]
}
~~~

If a workload only issues download URLs, omit the `s3:PutObject` statement. If it only issues upload URLs, omit `s3:GetObject`. Do not add `s3:ListBucket` if the application always knows the object key and does not need listing.

If objects use SSE-KMS, the signer also needs appropriate KMS permissions for the operation, such as `kms:GenerateDataKey` for upload and `kms:Decrypt` for download, along with an allowing key policy. These permissions live on the KMS key and do not replace `s3:GetObject`/`s3:PutObject`.

Attach the policy to the workload's IAM role:

- EC2: instance profile.
- ECS: task role.
- EKS: IRSA or EKS Pod Identity.
- Lambda: execution role.
- Local development: IAM Identity Center/SSO profile.

Keep Block Public Access enabled on the bucket and do not grant public ACLs. Presigned URLs work on private objects via their signature without making the bucket public.

### 6.2. Dependencies and presigner bean

Use the Spring Cloud AWS BOM compatible with Spring Boot and the S3 starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
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

The starter provides S3 client integration. Declare a dedicated `S3Presigner` bean if the application needs to generate presigned URLs:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration(proxyBeanMethods = false)
public class S3PresignerConfiguration {

    @Bean(destroyMethod = "close")
    S3Presigner s3Presigner(
            @Value("${app.storage.aws.region}") String region) {

        return S3Presigner.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

`DefaultCredentialsProvider` resolves credentials from the AWS environment: SSO/profile, web identity, ECS task role, or EC2 instance profile. Do not place static access keys and secret keys in `application.yml`.

### 6.3. Presigning GET to download documents

~~~java
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

public class S3SignedUrlAdapter {

    private final S3Presigner presigner;

    public S3SignedUrlAdapter(S3Presigner presigner) {
        this.presigner = presigner;
    }

    public DownloadGrant createDownloadGrant(
            String bucket,
            String objectKey,
            Duration ttl) {

        GetObjectRequest objectRequest = GetObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .build();

        GetObjectPresignRequest presignRequest =
                GetObjectPresignRequest.builder()
                        .signatureDuration(ttl)
                        .getObjectRequest(objectRequest)
                        .build();

        var signed = presigner.presignGetObject(presignRequest);

        return new DownloadGrant(
                URI.create(signed.url().toExternalForm()),
                "GET",
                Instant.now().plus(ttl));
    }
}
~~~

You can add `responseContentDisposition("attachment; filename=...")` to `GetObjectRequest` to instruct the browser to download the file with a display name. Sanitize the filename before putting it into the header; never concatenate arbitrary input.

### 6.4. Presigning PUT to upload

~~~java
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

public UploadGrant createUploadGrant(
        S3Presigner presigner,
        String bucket,
        String objectKey,
        String contentType,
        Duration ttl) {

    PutObjectRequest putRequest = PutObjectRequest.builder()
            .bucket(bucket)
            .key(objectKey)
            .contentType(contentType)
            .build();

    PutObjectPresignRequest presignRequest =
            PutObjectPresignRequest.builder()
                    .signatureDuration(ttl)
                    .putObjectRequest(putRequest)
                    .build();

    var signed = presigner.presignPutObject(presignRequest);

    return new UploadGrant(
            URI.create(signed.url().toExternalForm()),
            "PUT",
            Map.of("Content-Type", contentType),
            Instant.now().plus(ttl));
}
~~~

Because Content-Type is included in the signed request, the client must send the exact `Content-Type` header value signed by the backend. If the header differs or is missing, S3 may return `SignatureDoesNotMatch`.

Presigned PUT does not automatically limit the number of uses. While the URL is valid, anyone holding it can issue another PUT to the same key and overwrite the object. Use a unique object key per upload session, short TTLs, store the version token, and verify after upload. If create-only semantics are required, evaluate conditional writes with `If-None-Match: *` and sign the exact header according to your API/SDK capabilities.

### 6.5. Testing URLs

You can check the signer identity:

~~~bash
aws sts get-caller-identity
~~~

Test the URL with an HTTP client:

~~~bash
curl -I "PRESIGNED_GET_URL"
~~~

For PUT:

~~~bash
curl -X PUT \
  -H "Content-Type: text/plain" \
  --upload-file ./sample.txt \
  "PRESIGNED_PUT_URL"
~~~

Do not paste real URLs into tickets, chats, or shared terminal history. In the examples above, replace the placeholders with URLs received from the API in a test environment.

## 7. Google Cloud Storage — V4 Signed URLs

### 7.1. Signer permissions

The service account used to sign URLs must have permission to perform the operation encoded in the URL:

- Download: `storage.objects.get`.
- Upload: `storage.objects.create`.
- Overwriting an existing object may require additional delete permissions depending on operation semantics.
- Signing via IAM Credentials API: the runtime identity needs `iam.serviceAccounts.signBlob` on the signer service account.

The `iam.serviceAccounts.signBlob` permission is included in the `roles/iam.serviceAccountTokenCreator` role. Assign this role on the exact signer service account; do not grant it broadly at the project level if unnecessary.

### 7.2. Dependencies

Use the Spring Framework on Google Cloud BOM and Storage starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_GCP_VERSION</version>
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

The starter configures the `Storage` bean and ADC. Do not download service account JSON keys to production just to sign URLs.

### 7.3. ServiceAccountSigner requirement

`Storage.signUrl` requires a `ServiceAccountSigner`. Some credential types in ADC do not implement this interface. For example, credentials from a Google Cloud CLI user account are not automatically signers.

There are two common approaches:

1. Use credentials of a service account that supports signing and is managed securely.
2. Use the IAM Credentials API `signBlob` to sign remotely on behalf of the service account. The runtime identity is granted `roles/iam.serviceAccountTokenCreator` on the signer service account.

On Cloud Run, GKE, or environments using workload identity, inspect the actual credential type. Do not assume that simply injecting `Storage` guarantees `signUrl` can sign. The example below accepts a signer configured via credentials/workload identity:

~~~java
import com.google.auth.ServiceAccountSigner;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.concurrent.TimeUnit;

public class GcsSignedUrlAdapter {

    private final Storage storage;
    private final ServiceAccountSigner signer;

    public GcsSignedUrlAdapter(
            Storage storage,
            ServiceAccountSigner signer) {
        this.storage = storage;
        this.signer = signer;
    }

    public URL createDownloadUrl(
            String bucket,
            String objectKey) {

        BlobInfo blobInfo = BlobInfo.newBuilder(bucket, objectKey).build();

        return storage.signUrl(
                blobInfo,
                5,
                TimeUnit.MINUTES,
                Storage.SignUrlOption.withV4Signature(),
                Storage.SignUrlOption.httpMethod(HttpMethod.GET),
                Storage.SignUrlOption.signWith(signer));
    }
}
~~~

V4 signed URLs use Cloud Storage's XML API endpoint. Do not treat signed URLs as ordinary OAuth tokens or switch the endpoint to the JSON API.

### 7.4. Signing a PUT URL with Content-Type

~~~java
import com.google.auth.ServiceAccountSigner;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.concurrent.TimeUnit;

public URL createUploadUrl(
        Storage storage,
        ServiceAccountSigner signer,
        String bucket,
        String objectKey,
        String contentType) {

    BlobInfo blobInfo = BlobInfo.newBuilder(bucket, objectKey)
            .setContentType(contentType)
            .build();

    return storage.signUrl(
            blobInfo,
            10,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withContentType(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

The client sends `PUT` with the exact signed Content-Type:

~~~bash
curl -X PUT \
  -H "Content-Type: application/pdf" \
  --upload-file ./contract.pdf \
  "GCS_SIGNED_PUT_URL"
~~~

If the request does not send the exact signed headers, Cloud Storage rejects the signature. V4 signed URLs have a maximum lifetime of 7 days; for workload signers using IAM `signBlob`, choose short lifetimes for temporary access URLs.

### 7.5. Verifying configuration

Verify the signer service account and permissions:

~~~bash
gcloud iam service-accounts describe \
  SIGNER_SERVICE_ACCOUNT \
  --project=PROJECT_ID
~~~

Check object permissions on the bucket:

~~~bash
gcloud storage buckets get-iam-policy gs://training-document-vault
~~~

Test a signed GET:

~~~bash
curl -I "GCS_SIGNED_GET_URL"
~~~

If `Storage.signUrl` throws `IllegalStateException`, verify whether the credentials implement `ServiceAccountSigner`. If signing via the IAM Credentials API, check that the Service Account Credentials API is enabled and the `iam.serviceAccounts.signBlob` permission is granted.

## 8. Azure Blob Storage — User Delegation SAS

### 8.1. Choosing user delegation SAS

Azure has service SAS and account SAS signed with a storage account key. For Spring Boot applications using Microsoft Entra identities, prefer **user delegation SAS**:

- The backend authenticates using managed identity/workload identity or a service principal.
- The backend requests a user delegation key from Blob Storage.
- The backend uses that key to sign a SAS specifying the resource, permissions, and time window.
- The client receives the SAS URL and accesses the blob without an account key.

Microsoft recommends user delegation SAS whenever possible because storage account keys do not have to be shared. A user delegation key has a maximum lifetime of 7 days; the SAS must fall within the key's validity window.

### 8.2. RBAC for the signer

Two types of permissions must be separated:

| Scope | Role/permission | Purpose |
| --- | --- | --- |
| Storage account scope | `Storage Blob Delegator` | Allows calling `getUserDelegationKey` |
| Container scope, download | `Storage Blob Data Reader` | Allows the signer to read blobs |
| Container scope, upload | `Storage Blob Data Contributor` | Allows the signer to create/write blobs |

`getUserDelegationKey` operates at the storage account level. Therefore, `Storage Blob Delegator` must be assigned at the storage account, resource group, or subscription scope. Data roles can be scoped to a specific container.

The effective permission of a user delegation SAS is the intersection of the data permissions granted to the signer via Azure RBAC and the permissions encoded in the SAS. If the SAS has the read flag but the signer lacks blob read permission at the appropriate scope, the client still cannot read. Conversely, a SAS cannot escalate permissions beyond those of the signer.

Do not grant `Storage Blob Data Owner` or a storage account key just to sign a read-only SAS.

### 8.3. Dependencies and BlobServiceClient

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AZURE_VERSION</version>
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
</dependencies>
~~~

Use `DefaultAzureCredential` to obtain tokens from managed identity or workload identity in the runtime environment:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureBlobConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(
            @org.springframework.beans.factory.annotation.Value(
                    "${app.storage.azure.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
~~~

In local environments, `DefaultAzureCredential` can use the Azure CLI or developer credentials. In production, prefer managed identity/workload identity. Never put storage account keys or connection strings containing keys in source code.

### 8.4. Generating a user delegation key and read-only SAS

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.UserDelegationKey;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import com.azure.storage.common.sas.SasProtocol;
import java.net.URI;
import java.time.OffsetDateTime;

public class AzureSasAdapter {

    private final BlobServiceClient serviceClient;

    public AzureSasAdapter(BlobServiceClient serviceClient) {
        this.serviceClient = serviceClient;
    }

    public URI createReadUrl(
            String container,
            String blobName) {

        OffsetDateTime now = OffsetDateTime.now();
        OffsetDateTime start = now.minusMinutes(5);
        OffsetDateTime expiry = now.plusMinutes(5);

        UserDelegationKey delegationKey =
                serviceClient.getUserDelegationKey(start, expiry);

        var blob = serviceClient
                .getBlobContainerClient(container)
                .getBlobClient(blobName);

        BlobSasPermission permission =
                new BlobSasPermission().setReadPermission(true);

        BlobServiceSasSignatureValues values =
                new BlobServiceSasSignatureValues(expiry, permission)
                        .setStartTime(start)
                        .setProtocol(SasProtocol.HTTPS);

        String sasToken =
                blob.generateUserDelegationSas(values, delegationKey);

        return URI.create(blob.getBlobUrl() + "?" + sasToken);
    }
}
~~~

This example generates a user delegation key per request to illustrate the flow clearly. In production, you can cache the key for a safe validity period and sign multiple SAS tokens with it; do not keep the key past its validity or log key material.

The SAS only has read permission. Do not grant write, delete, or list if the client only downloads a single blob.

### 8.5. Creating an upload SAS

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.UserDelegationKey;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import com.azure.storage.common.sas.SasProtocol;
import java.net.URI;
import java.time.OffsetDateTime;

public URI createUploadUrl(
        BlobServiceClient serviceClient,
        String container,
        String blobName) {

    OffsetDateTime now = OffsetDateTime.now();
    OffsetDateTime start = now.minusMinutes(5);
    OffsetDateTime expiry = now.plusMinutes(10);

    UserDelegationKey key =
            serviceClient.getUserDelegationKey(start, expiry);

    var blob = serviceClient
            .getBlobContainerClient(container)
            .getBlobClient(blobName);

    BlobSasPermission permission = new BlobSasPermission()
            .setCreatePermission(true)
            .setWritePermission(true);

    BlobServiceSasSignatureValues values =
            new BlobServiceSasSignatureValues(expiry, permission)
                    .setStartTime(start)
                    .setProtocol(SasProtocol.HTTPS);

    String sasToken = blob.generateUserDelegationSas(values, key);

    return URI.create(blob.getBlobUrl() + "?" + sasToken);
}
~~~

The upload SAS has create/write permissions on that exact blob. The client uses `PUT` according to the Blob Storage API and sends the appropriate headers. Never issue a container-wide SAS if only a single object needs to be uploaded.

### 8.6. Lifetime and revocation

A user delegation key can be used to sign multiple SAS tokens until the key expires. Set key validity long enough to sign short-lived SAS tokens, but never exceeding 7 days. SAS expiry must fall within the key validity window.

When a SAS leak is detected, you can revoke user delegation keys on the storage account, change RBAC permissions, or delete/modify the resource state. Revoking keys can affect many SAS tokens signed with that key; evaluate the blast radius carefully.

## 9. One Business API for Three Providers

### 9.1. Provider configuration

Only one adapter is activated in the lab via a Spring profile:

~~~yaml
app:
  storage:
    provider: aws
    bucket: training-document-vault
    upload-ttl: 10m
    download-ttl: 5m
    max-file-size: 10485760
    allowed-content-types:
      - application/pdf
      - image/png
      - image/jpeg
~~~

Bucket name, endpoint, and region are configured per environment. Never accept these values from user requests.

### 9.2. Upload session creation service

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final DocumentObjectStorage objectStorage;
    private final DocumentAuthorization authorization;

    public DocumentService(
            DocumentRepository repository,
            DocumentObjectStorage objectStorage,
            DocumentAuthorization authorization) {
        this.repository = repository;
        this.objectStorage = objectStorage;
        this.authorization = authorization;
    }

    public UploadSessionResponse createUpload(
            AuthenticatedUser user,
            CreateDocumentRequest request) {

        authorization.requireCanCreateDocument(user);

        validateUploadRequest(request);

        UUID documentId = UUID.randomUUID();
        String objectKey = "documents/" + user.tenantId()
                + "/" + documentId;

        DocumentRecord record = DocumentRecord.pending(
                documentId,
                user.tenantId(),
                objectKey,
                request.filename(),
                request.contentType(),
                request.sizeBytes());

        repository.save(record);

        UploadGrant grant = objectStorage.createUploadGrant(
                record.bucketName(),
                objectKey,
                request.contentType(),
                Duration.ofMinutes(10));

        Instant expiry = grant.expiresAt();
        repository.updateUploadExpiry(documentId, expiry);

        return new UploadSessionResponse(
                documentId,
                grant.url(),
                grant.method(),
                grant.requiredHeaders(),
                expiry);
    }

    private void validateUploadRequest(CreateDocumentRequest request) {
        if (request.sizeBytes() <= 0 || request.sizeBytes() > 10_485_760) {
            throw new IllegalArgumentException("Invalid file size");
        }
        if (!request.contentType().matches(
                "application/pdf|image/png|image/jpeg")) {
            throw new IllegalArgumentException("Unsupported Content-Type");
        }
    }
}
~~~

`AuthenticatedUser`, `DocumentRepository`, `DocumentRecord`, `CreateDocumentRequest`, and `UploadSessionResponse` are illustrative domain models. Do not hold a database transaction open while waiting for the client to upload the file. If URL signing fails after the record is saved, mark the session as failed or let a reconciliation job handle stale `PENDING_UPLOAD` records.

Do not trust `filename`, `contentType`, or `sizeBytes` declared by the client. They are only used to initialize the session and perform preliminary checks; the backend verifies the actual object after upload.

### 9.3. Session creation endpoint

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping
    public ResponseEntity<UploadSessionResponse> create(
            @RequestBody CreateDocumentRequest request,
            @AuthenticationPrincipal AuthenticatedUser user) {

        UploadSessionResponse response =
                documentService.createUpload(user, request);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(response);
    }
}
~~~

In a real application, `AuthenticatedUser` is resolved from the Spring Security principal or an equivalent authentication service. Never bind the principal from the JSON request body.

### 9.4. Direct client upload

Sample response:

~~~json
{
  "documentId": "4c9d8b21-2c71-4e10-8d34-1d7e2a2c4f11",
  "method": "PUT",
  "url": "https://storage-provider.example/signed-request",
  "requiredHeaders": {
    "Content-Type": "application/pdf"
  },
  "expiresAt": "2026-11-24T11:20:00Z"
}
~~~

The client sends the exact HTTP method and headers returned by the backend:

~~~javascript
const response = await fetch(uploadUrl, {
  method: "PUT",
  headers: requiredHeaders,
  body: file
});

if (!response.ok) {
  throw new Error("Upload failed");
}
~~~

This is a browser example. Do not log `uploadUrl`, store URLs in local storage, or send URLs to analytics. If the upload fails because the URL expired, the client calls the API to create a new session according to backend policy.

## 10. Verifying the Object After Upload

### 10.1. Why finalize?

A client reporting upload success is not enough to mark a document `AVAILABLE`. The backend needs to read object metadata from storage and verify:

- Whether the object exists.
- Whether the actual size complies with policy.
- Whether the Content-Type is on the allowlist.
- Whether the checksum is valid.
- Whether the object key matches the issued session.
- Whether Generation/ETag is saved to detect future updates.

### 10.2. Complete endpoint

~~~java
@PostMapping("/{documentId}/complete")
public ResponseEntity<DocumentView> complete(
        @PathVariable UUID documentId,
        AuthenticatedUser user) {

    DocumentView result =
            documentService.verifyUploadAndComplete(documentId, user);

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
}
~~~

The service must check tenant ownership before calling storage. If the object does not exist yet, keep the pending state or return a retryable error. If size/type/checksum is invalid, transition to `REJECTED`, delete or quarantine the object per policy, and write an audit log.

### 10.3. Reading metadata via provider adapter

S3 adapter example using `HeadObject`:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public StoredObjectMetadata headS3(
        S3Client client,
        String bucket,
        String key) {

    var response = client.headObject(
            HeadObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());

    return new StoredObjectMetadata(
            response.contentLength(),
            response.contentType(),
            response.versionId() != null
                    ? response.versionId()
                    : response.eTag(),
            response.checksumSHA256());
}
~~~

GCS can use `Storage.get(BlobId.of(bucket, key))` and read `getSize()`, `getContentType()`, `getGeneration()`, and checksums. Azure uses `BlobClient.getProperties()` and reads blob size, Content-Type, ETag, and checksum fields appropriate for the SDK version.

Do not treat ETag as SHA-256. ETag has provider-, encryption-, and multipart-upload-specific semantics. If cross-provider integrity verification is needed, compute SHA-256 on the client or backend and verify using the checksum mechanism supported by each provider.

### 10.4. Avoiding races during finalization

A presigned PUT can be reused until it expires. If an object is overwritten between the backend HEAD call and the database update, the record may store a token that is no longer the current version.

Use a dedicated object key per upload session and store the returned version token. If the provider supports conditional create/write, sign the appropriate precondition or use a server-side API with a generation/ETag condition. If the bucket has versioning enabled, store the specific version ID/generation and use that version when reading. When uploads might be replayed, detect generation/ETag changes after finalization and do not automatically treat a newer object as an approved document.

## 11. Issuing Authorized Download URLs

### 11.1. Authorizing before signing

A download API must not accept arbitrary buckets and keys. Secure flow:

1. Authenticate the caller.
2. Load the document record from the database.
3. Verify tenant ownership and read permission on the document.
4. Confirm the state is `AVAILABLE`.
5. Retrieve the bucket/object key from the record.
6. Sign a GET URL with a short TTL.
7. Write audit metadata about the URL issuance, without logging the token.
8. Return the URL with `Cache-Control: no-store`.

### 11.2. Download URL issuance service

~~~java
public DownloadSessionResponse createDownload(
        UUID documentId,
        AuthenticatedUser user) {

    DocumentRecord document = repository.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);

    authorization.requireCanRead(user, document);

    if (document.state() != DocumentState.AVAILABLE) {
        throw new IllegalStateException("Document is not ready");
    }

    DownloadGrant grant = objectStorage.createDownloadGrant(
            document.bucketName(),
            document.objectKey(),
            Duration.ofMinutes(5));

    audit.recordDownloadUrlIssued(
            document.id(),
            user.id(),
            grant.expiresAt());

    return new DownloadSessionResponse(
            document.id(),
            grant.url(),
            grant.method(),
            grant.expiresAt());
}
~~~

Each time the user needs to download again, the backend checks permissions and issues a fresh URL. Do not store URLs for long-term reuse.

### 11.3. Do not issue URLs for unverified documents

If a document is in `PENDING_UPLOAD`, `VERIFYING`, or `REJECTED` state, never issue a download URL. If a document has been logically deleted, no new URLs may be created even if object storage cleanup has not run yet.

Previously issued URLs may continue working until they expire. Therefore, TTLs must be short and deletion workflows must account for still-valid URLs.

## 12. CORS for Direct Browser Upload/Download

CORS allows browsers to send cross-origin requests to object storage. CORS does not grant access privileges; requests must still carry valid signatures.

CORS should restrict:

- Origins of the official frontend.
- Required HTTP methods: GET, PUT, HEAD.
- Request headers: Content-Type and any checksum headers used.
- Response headers the browser needs to read: ETag or generation headers if needed.
- Max age of preflight cache.

Conceptual configuration example:

~~~json
[
  {
    "origin": ["https://app.example.com"],
    "method": ["GET", "PUT", "HEAD"],
    "responseHeader": ["Content-Type", "ETag", "x-goog-generation"],
    "maxAgeSeconds": 1800
  }
]
~~~

CORS structure and field names differ across S3, GCS, and Azure. Translate the sample config into each provider's official schema before applying. Do not use `origin: ["*"]` in production if the frontend only lives on specific domains.

If the browser reports a CORS error while `curl` succeeds, check OPTIONS preflight, allowed origins, allowed headers, and exposed response headers. If `curl` also returns 403, check the signature, credential expiry, HTTP method, and IAM/RBAC.

## 13. Validating Uploads, File Types, and Sizes

### 13.1. Do not trust client-supplied Content-Type

A Content-Type header sent by the client does not prove the actual contents are PDF or PNG. The backend needs to inspect file signatures/magic bytes or run a content scanner after upload.

Recommended workflow:

1. Client declares content type and size to create a session.
2. Backend checks the allowlist and declared limits.
3. Backend signs the URL with Content-Type if the provider supports it.
4. Client uploads.
5. Backend calls HEAD to inspect size and metadata.
6. Worker reads partial or full bytes to verify file signature, checksum, and malware.
7. Transition state to `AVAILABLE` only after all required checks pass.

### 13.2. Size limits

Do not assume presigned PUT/SAS automatically enforces every business size limit. If a hard limit is required:

- S3: consider presigned POST policies with `content-length-range`, or proxy uploads through a backend/gateway.
- GCS: consider resumable uploads/sessions and appropriate preconditions; still verify size after upload.
- Azure: SAS restricts resource and permissions, and does not natively enforce arbitrary client content-length policies.

If size is only checked after upload, oversized objects have already been stored and can incur cost. Combine per-tenant quotas, rate limiting, upload session expiry, cleanup, and appropriate upload policies.

### 13.3. Checksums and integrity

When a provider supports checksum headers, sign the checksum into the request so the client cannot alter the header after the URL is issued. After upload, read the checksum or download bytes to verify as required.

Do not use ETag as a universal checksum across all three providers. Multipart uploads, server-side encryption, and differing implementations can make ETag unequal to a content hash.

## 14. Expired URLs, Revocation, and Error Handling

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| S3 `Request has expired` | URL expired or signer temporary credentials expired | Issue a new URL after re-authorizing |
| S3 `SignatureDoesNotMatch` | Wrong region, method, or signed header | Compare actual request against signed method/headers |
| GCS 403 | Signer lacks object permission or invalid signature | Check signer identity, IAM, clock skew, and canonical request |
| GCS `IllegalStateException` on sign | Credentials do not implement `ServiceAccountSigner` | Configure signer or IAM `signBlob` |
| Azure 403 | SAS expired, missing permission, wrong resource, or expired delegation key | Check `sp`, `sr`, `st`, `se`, key validity, and RBAC |
| Browser CORS error | Mismatched CORS origin/method/header | Check OPTIONS preflight and CORS config |
| Upload returns 200 but document is not READY | Complete not called or verification failed | Check object HEAD, checksum, size, and state |
| URL expired but object remains | URL TTL is not object lifecycle | Delete object per business rules or lifecycle rule |
| URL leaked | Others can use bearer URL within its validity window | Revoke per provider capability, delete/rotate object, or wait for expiry; investigate audit logs |

Never retry the same URL after it expires. The backend must re-authenticate the user, verify document state, and sign a fresh URL.

## 15. Security and Operations for the Document Repository

### 15.1. Private buckets/containers

- Disable public access and public ACLs.
- Enable encryption at rest per provider policy.
- Use least-privilege IAM/RBAC for the runtime signer.
- Separate upload, download, cleanup, and provisioning roles when appropriate.
- Enable audit logging for object operations and role assignments.
- Use TLS/HTTPS for all URLs.
- Never place storage account keys or service account JSON in source code.

### 15.2. Never log signed URLs

Query strings may contain signatures, credential scopes, expiry timestamps, and SAS permissions. Logging the full URL is equivalent to logging a bearer credential.

Log only:

- Internal document ID.
- Normalized tenant ID.
- Provider and operation.
- Object key protected according to policy.
- Expiry timestamp.
- Signer principal or role session ID.
- Request ID and outcome.

Never log URLs, SAS tokens, access tokens, or file contents.

### 15.3. Auditing issuance

You can create a `document_access_grants` table to track:

- Document ID.
- Requesting user ID.
- Operation GET/PUT.
- Provider and signer identity.
- Issued time and expiry time.
- Upload session ID or correlation ID.
- Upload/finalization status.

Never store tokens or full URLs in the audit table. Audit logs help investigate who requested access and during which time window.

### 15.4. Orphan cleanup and lifecycle

There are two types of data requiring cleanup:

1. Expired `PENDING_UPLOAD` database records with no uploaded object.
2. Uploaded objects that were never finalized or were rejected.

Use a scheduled worker to find expired sessions and check storage objects. Delete orphaned objects per policy; do not merely delete the database record and leave the object behind in the bucket.

Lifecycle rules can clean up temporary prefixes such as `staging/` after a retention period. Lifecycle rules are a cost safety net, not a replacement for the business state machine and authorization. When buckets enable versioning or soft delete, account for noncurrent versions and soft-deleted storage in cost calculations.

## 16. Testing

### 16.1. Unit tests for the domain service

Verify:

- Users outside the tenant cannot create an upload session.
- Content-Types outside the allowlist are rejected.
- Declared sizes exceeding the limit are rejected.
- Object keys are server-generated and do not contain raw filenames.
- Documents not yet `AVAILABLE` are not issued download URLs.
- Users without read permissions on a document do not receive URLs.
- Upload grants only permit PUT and use policy-compliant TTLs.
- Download grants only permit GET and use shorter TTLs than upload sessions if policy requires.
- Signed URLs are not written to the database or logs.

### 16.2. Integration tests with real providers

Use a dedicated test bucket/container and workload identity:

1. Create private object storage.
2. Grant the signer role at the proper scope.
3. Create an upload session from Spring Boot.
4. Use the URL to upload a small file with the right method/headers.
5. Call the complete endpoint and verify object metadata.
6. Generate a download URL and download the file.
7. Test the URL after expiration; expect denial.
8. Test the wrong HTTP method; expect denial.
9. Test altering the signed Content-Type; expect denial.
10. Test accessing a different object key; expect denial.
11. Test a user from another tenant requesting a download; backend must reject before signing.
12. Verify that URLs do not appear in logs.
13. Verify CORS from an allowed browser origin and a disallowed origin.
14. Clean up objects, versions, and test sessions after testing.

### 16.3. Testing replay and race conditions

Signed URLs are not single-use tokens. Test:

- Sending PUT twice before expiry.
- Calling complete twice.
- Calling complete before upload finishes.
- Overwriting the object after the document is `AVAILABLE`.
- Using a download URL after the document has been marked deleted.
- Uploading an object larger than the declared size.
- Uploading content that mismatches the Content-Type.
- Sending the same URL from a different client.

The application must make complete/finalize idempotent, store generation/version tokens, verify the current object, and prevent a replay from altering an approved document without a new versioning workflow.

### 16.4. Emulators and real cloud tests

LocalStack, Azurite, or suitable emulators can help test parts of the client API. However, signing behavior, IAM/RBAC, URL expiry, CORS, and cloud-specific policies require integration tests against real test projects/accounts. Never conclude signer permissions or URL semantics solely from mocks.

## 17. Comparing the Three Providers

| Aspect | Amazon S3 | Google Cloud Storage | Azure Blob Storage |
| --- | --- | --- | --- |
| Temporary URL | Presigned URL | V4 Signed URL | SAS URL |
| Java signing API | `S3Presigner` | `Storage.signUrl` | `generateUserDelegationSas` |
| Signing identity | AWS IAM role/user credentials | Service account signer | Microsoft Entra principal + user delegation key |
| Download permission | `s3:GetObject` | `storage.objects.get` | SAS `read` + RBAC data permission |
| Upload permission | `s3:PutObject` | `storage.objects.create` | SAS `create`/`write` + RBAC data permission |
| Max signing/key duration | SigV4 URLs max 7 days; temporary credentials may be shorter | V4 max 7 days; remote `signBlob` should use short TTLs | User delegation key max 7 days |
| Signed headers | Request headers can be signed | Content-Type and selected headers can be signed | SAS permissions and signed fields per SAS |
| Browser support | Requires bucket CORS | Requires bucket CORS | Requires Blob service CORS |
| Revocation | Credential/policy/object; URLs generally lack individual revoke buttons | Signer key/permission or object; URLs may be affected by key rotation | Revoke delegation keys/RBAC or resource; impact can be broad |
| Version token | Version ID/ETag | Generation/metageneration | Version ID/ETag |

Do not mechanically map presigned URLs, signed URLs, and SAS into a single token type with identical semantics. Adapters should standardize the `createUploadGrant`/`createDownloadGrant` contract, while provider implementations keep methods, headers, signer identities, version tokens, and revocation mechanisms distinct.

## 18. Comprehensive Hands-On Exercise

**Context:** Build a document repository for a multi-tenant Spring Boot application. Users upload PDF contracts, the backend verifies the files, and issues time-limited download URLs. Files must reside in a private bucket/container and cross-tenant access must be prevented.

### Task A — Storage and metadata

1. Create a dedicated bucket/container for the lab environment.
2. Disable public access.
3. Create the `documents` table and state machine.
4. Generate object keys from the authenticated tenant and a UUID.
5. Store the original filename, content type, size, checksum, and version token in the database.

### Task B — Upload URL

1. Create a dedicated signer identity.
2. Grant least-privilege upload permissions for the exact prefix/container.
3. Write an adapter generating presigned PUT, GCS V4 PUT, or Azure create/write SAS.
4. Choose a 5–10 minute TTL.
5. Return the URL along with required headers.
6. Upload a file directly from the browser.

### Task C — Verify and finalize

1. Create the complete endpoint.
2. Read object metadata using HEAD/properties.
3. Verify size, Content-Type, and checksum.
4. Verify tenant/object key and session state.
5. Store the generation/version token.
6. Transition state to `AVAILABLE` only after verification succeeds.

### Task D — Download URL

1. Authenticate user and tenant.
2. Check document read permission.
3. Only issue URLs for `AVAILABLE` documents.
4. Sign a GET URL with a 2–5 minute TTL.
5. Return `Cache-Control: no-store`.
6. Verify the URL downloads the object without requiring user cloud credentials.

### Task E — Security and operations

- Test expired URLs, wrong methods, and wrong Content-Type.
- Try replaying PUT and observe the new generation.
- Verify that a user from another tenant cannot obtain a URL.
- Configure CORS only for the frontend origin.
- Enable audit logging without logging URLs/tokens.
- Clean up expired upload sessions and orphaned objects.
- Compare S3 presigned URLs, GCS V4 signed URLs, and Azure user delegation SAS.

**Acceptance criteria:** The application stores metadata in the database and bytes in object storage; the signer uses workload identity; the bucket/container is private; upload/download URLs are only issued after authorization; TTLs are short; objects are verified before becoming `AVAILABLE`; and tests prove that wrong methods, expired URLs, and cross-tenant access are denied.

## 19. Key Takeaways

- Document metadata and state belong in the database; bytes belong in object storage.
- Object keys must be backend-generated; original filenames are stored separately.
- Presigned URLs, GCS signed URLs, and Azure SAS are bearer capabilities; anyone holding a URL can use it within its signed scope.
- The backend must authorize the user and tenant before issuing any URL.
- S3 uses `S3Presigner`; GCS uses `Storage.signUrl` with V4 and `ServiceAccountSigner`; Azure prefers user delegation SAS.
- URL TTL depends on both the configured expiry and the lifetime of the signer credential or delegation key.
- Signed PUT/SAS does not guarantee single-use URLs; use unique object keys, precondition/version guards, and idempotent finalization.
- Clients uploading directly must send the exact signed method and headers.
- Verify size, checksum, Content-Type, and version token before marking a document `AVAILABLE`.
- CORS only controls browser cross-origin behavior; CORS does not replace IAM/RBAC.
- Never log or store full URLs/SAS tokens; return responses with `Cache-Control: no-store`.
- An expired URL does not delete the object; use a state machine, cleanup worker, and lifecycle policies.

### References

- [AWS SDK for Java 2.x — Work with S3 presigned URLs](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-presign.html)
- [Amazon S3 — Download and upload objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [AWS SDK for Java 2.x — S3Presigner API](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/s3/presigner/S3Presigner.html)
- [Spring Cloud AWS reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Cloud Storage — Signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)
- [Cloud Storage Java — Storage.signUrl](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Cloud Storage — Create signatures and signBlob](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures)
- [Cloud Storage — CORS configuration](https://docs.cloud.google.com/storage/docs/cross-origin)
- [Azure Storage — Create a user delegation SAS with Java](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-user-delegation-sas-create-java)
- [Azure Storage — Built-in RBAC roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/storage)
- [Azure Storage — Get User Delegation Key permissions](https://learn.microsoft.com/en-us/rest/api/storageservices/get-user-delegation-key)
- [Azure Storage — SAS overview and security](https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview)
- [Spring Cloud Azure reference](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/)

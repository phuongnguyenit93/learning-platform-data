# Time Limits, Scope, and Permissions for Shared URLs and Tokens

A signed file download URL or bearer token lets a recipient access a resource without needing a cloud account. This mechanism is convenient for sharing contracts, images, and reports, or receiving partner uploads. However, **anyone who holds the URL/token can use it within the granted scope**. If a link is forwarded, written to logs, saved in browser history, or captured in analytics, others can use it just like the intended recipient.

Secure design must constrain **time**, **resource**, **action**, **intended recipient**, and **revocation capability** together. A link granting read-only access to one object for 5 minutes carries far less risk than a link granting read/write access to an entire container for days. A token with explicit audience and scope is far safer than a broadly scoped token. Short lifetimes alone cannot compensate for overly broad permissions or leaked URLs.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, covering identity/permissions, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. The focus of this lesson is generating time-bounded, least-privilege share links, properly using signed URLs/SAS, protecting bearer tokens, managing revocation, and auditing usage.

## 1. Learning Objectives and Real-World Scenario

After this lesson, you will be able to:

1. Distinguish among signed share URLs, SAS, presigned URLs, signed URLs, and OAuth access tokens.
2. Explain why shared URLs/tokens are bearer credentials and anyone holding them can exercise them.
3. Design TTLs, resource scopes, HTTP methods, permissions, audiences, and network restrictions.
4. Generate S3 presigned URLs, Azure Blob user delegation SAS, and Google Cloud Storage signed URLs.
5. Design a share-link service in Spring Boot with expiry, revocation, auditing, and quotas.
6. Distinguish revocable links from links that only expire based on their signature.
7. Protect URLs/tokens from logs, browser history, referrers, analytics, tickets, and chat.
8. Test expiration, wrong permissions, wrong objects, replay, revocation, and oversized uploads.

Running scenario: **document-service** stores contracts in object storage. Signed-in users request to share a contract with an external partner for a short window. The partner has no cloud account. The system must issue a read-only link for that exact object, expire it after a set duration, support on-demand revocation, and audit who created the link.

~~~mermaid
flowchart TD
    U["Signed-in user"] --> API["Spring Boot Share API"]
    API --> AUTH["Authenticate + authorize object access"]
    AUTH --> POLICY["Create grant: object, action, TTL, recipient"]
    POLICY --> SIGN["Cloud signer: S3 / SAS / GCS"]
    SIGN --> URL["Short-lived signed URL"]
    URL --> R["Recipient"]
    R --> STORE["Managed object storage"]
    API --> AUDIT["Audit: creator, object, expiry, permission"]
    STORE --> LOG["Access logs / monitoring"]
~~~

**Key principle:** A signed URL does not prove the identity of the person clicking the link. It proves the request carries a valid signature. If you must know exactly who the recipient is, authenticate them via the application or another identity mechanism before granting download access.

## 2. Distinguishing URL and Token Types

### 2.1. Signed URL, presigned URL, and SAS

These are URLs containing authentication/signature parameters in the query string or URL structure. Recipients can call the storage service directly:

- AWS S3 presigned URL: SigV4 signature for a specific HTTP method and object.
- Azure Storage SAS: query string token specifying resource, permissions, and time interval.
- Google Cloud Storage signed URL: V4 signature covering method, object, timestamps, and signed headers.

Common characteristics:

- No need to share cloud access keys/secret keys with recipients.
- The link creator must hold the necessary permissions to perform the signed action.
- Anyone holding the link can use it within the signature's limits.
- Links can be copied, forwarded, saved in browser history, or logged.
- Expiration time is an important boundary, though not the only control.

### 2.2. OAuth access tokens and bearer tokens

Access tokens are typically sent in the HTTP `Authorization` header:

~~~http
Authorization: Bearer eyJhbGciOi...
~~~

A token represents a subject/client's permissions for a specific audience, scope, and validity window. The resource server validates the token and checks permissions on every request.

Do not place OAuth bearer tokens in URL query parameters. URLs routinely appear in browser history, reverse proxy logs, analytics, `Referer` headers, and observability systems. RFC 6750 recommends transmitting bearer tokens in the `Authorization` header or TLS-protected request body, never in page URLs.

### 2.3. Application share links

An application can issue its own links such as:

~~~text
https://share.example.com/s/opaque-random-token
~~~

The random token is looked up in a database to determine:

- The shared resource/object.
- The creator and intended recipient.
- Granted permissions.
- Expiration and revocation timestamps.
- Usage limits or consumed state.
- Identity verification, OTP, or email requirements.

This model fits well when per-link revocation, access count limits, or recipient authentication are needed. The application validates the token before streaming content or issuing a very short-lived cloud URL.

### 2.4. Comparison

| Mechanism | Where are permissions decided? | Can an individual link be revoked? | Does recipient need a cloud identity? |
| --- | --- | --- | --- |
| S3 presigned URL | Signature, IAM principal, and bucket/object policies | No per-URL revoke action; can block via credentials/policy/resource | No |
| Azure SAS | SAS permissions, resource, expiry, and signing key/policy | Depends on SAS type; stored access policies support certain service SAS tokens | No |
| GCS signed URL | Signature, signer permissions, and object policies | Typically requires revoking key/signing identity or blocking resource; no per-URL revoke button | No |
| OAuth access token | Authorization server issues scope/audience; resource server verifies | Depends on token format, introspection/revocation, and lifetime | Requires identity/token |
| Application share link | Application database/policies | Yes, if every request goes through the share service | Not necessarily; can require OTP/login |

A signed URL is a form of bearer capability: authority is granted to whoever holds the link. Never post links in public channels or treat them like ordinary URLs.

## 3. Designing Time Limits

### 3.1. Short TTLs matched to purpose

Lifetimes should reflect how long a recipient needs to complete the task:

| Use case | Starting TTL to consider | Notes |
| --- | --- | --- |
| In-session document preview | 1–5 minutes | Can be re-issued while the user remains authorized |
| Partner contract download | 5–15 minutes | Verify recipient before issuing link |
| Single file upload from browser | 5–15 minutes | Bind method, object key, and headers |
| Temporary report download | 5–30 minutes | Delete temporary files per retention |
| Batch integration with partner | Aligned to schedule, usually shorter than long-lived credentials | Consider workload identity instead of long-lived links |

These are design guidelines, not mandatory cloud limits. Balance file transfer duration, slow networks, retries, and user experience. For large files, a request started before expiry may continue past expiration depending on the service; subsequent reconnections after expiry will generally be rejected.

### 3.2. Do not confuse URL TTL with signing credential TTL

The effective lifetime is typically the shortest among several limits:

- Expiry encoded in the URL/token.
- Expiry of the credentials/session that signed the URL.
- Disabling/rotation of the signing key or identity.
- Rejection by a resource policy or network policy.
- Revocation of an application share grant if requests route through the app.

For example, an AWS S3 URL requesting a 60-minute lifetime but signed using temporary role credentials with 20 minutes remaining will only work until those credentials expire. Setting a 7-day expiry does not extend a role session to 7 days.

### 3.3. Clocks and start times

Cloud signers and storage services rely on UTC time. Clock drift on the signing host can cause URLs to be not yet valid or to expire prematurely.

- Synchronize time with NTP on nodes/VMs.
- Use UTC/`Instant` in Java.
- Never trust the browser's clock to compute expiry.
- If setting a start time, account for small clock skew per provider guidance.
- Do not set start times far in the past, as doing so widens the usage window.
- Test boundaries just before, at, and immediately after expiry.

### 3.4. Maximum lifetimes by provider

| Provider | Key limits |
| --- | --- |
| Amazon S3 | SigV4 presigned URLs via SDK/CLI can be set up to 7 days; if using temporary credentials, the URL stops working when credentials expire or are revoked earlier |
| Azure Storage | User delegation SAS has a maximum lifetime of 7 days; account SAS/service SAS have different rules and are subject to account/policy settings |
| Google Cloud Storage | V4 signed URLs allow up to 604800 seconds (7 days); signatures depend on the key/signing identity and may become invalid earlier if the key is rotated |

Do not use the maximum as your default TTL. For human sharing, a few minutes or hours is usually far more appropriate than days.

## 4. Restricting Resource Scope and Actions

### 4.1. Target a single specific resource

A share grant should explicitly specify:

- Bucket/container.
- Object key or blob name.
- Object version/generation if business logic requires pinning a version.
- Allowed HTTP method: `GET`, `PUT`, or `HEAD`.
- Content type and checksum for uploads.
- Response disposition if download should be forced instead of inline rendering.
- Tenant and business object ID.
- Start/expiration timestamps.

Avoid generating links for an entire bucket/container when the recipient only needs one file. Do not place broad prefixes in URLs without an actual requirement.

### 4.2. Grant only required permissions

| Use case | Permission |
| --- | --- |
| File download | `GET`/read |
| Upload new file | `PUT`/create/write for a single object |
| Read metadata | `HEAD`/read properties if needed |
| Delete file | `DELETE` only when explicitly required by business logic |
| List bucket/container | Never grant on a single-file download link |
| Overwrite existing object | Avoid unless necessary; use random object keys or creation preconditions |

An upload URL must not simultaneously allow read, delete, and list. A download URL must not be signed for `PUT`/`DELETE`.

### 4.3. Constraining upload requests

When issuing upload links:

- Generate the object key server-side; never let clients choose arbitrary keys.
- Bind the HTTP method and required `Content-Type`/headers into the signature.
- Require checksum or integrity headers when supported by the provider.
- Verify file size after upload before promoting the object to active status.
- Run malware/content-type scanning in an appropriate pipeline.
- Use a quarantine prefix/container for unverified files.
- Prevent overwriting existing objects using unique keys or service preconditions where supported.
- Never grant list/delete permissions.

Some signed `PUT` URLs cannot enforce strict size limits the way policy-based form uploads can. If hard size enforcement is required prior to storage, use a presigned `POST` policy (AWS), proxy uploads through a backend, or an equivalent policy-backed upload mechanism; do not assume signing a `PUT` URL alone suffices.

### 4.4. Binding recipients

Plain signed URLs are not tied to a specific email/person. Anyone holding the link can use it. When recipient binding is needed:

1. The recipient opens an application share link.
2. The app requires sign-in or an OTP sent to a verified channel.
3. The server checks recipient, tenant, expiry, revocation, and permissions.
4. The server streams the file or issues a fresh signed URL with a very short TTL.
5. Audit both link issuance and download events.

OTPs need rate limiting, short lifetimes, brute-force protection, and no plaintext logging. Never treat a client-supplied email address on each request as proof of identity.

### 4.5. Network and device constraints

Some providers let you restrict IP ranges or endpoints:

- Azure SAS supports signed IP ranges and HTTPS-only protocol restrictions.
- AWS IAM/bucket policies can enforce `aws:SourceIp`, `aws:SourceVpc`, or `aws:SourceVpce` depending on the scenario.
- GCP signed URLs are generally not intended for IP-binding end users; consider proxies/application gateways if needed.

IP restrictions can break mobile users, NAT gateways, or changing partner networks. Apply them only when operationally required and tested.

## 5. Application Share-Link Service in Spring Boot

### 5.1. Separating share grants from signed URLs

A flexible architecture stores share permission metadata in a database. A signed URL is generated only when the recipient actually requests access:

~~~mermaid
sequenceDiagram
    participant Owner as Owner
    participant API as Spring Boot
    participant DB as Share Grant DB
    participant Signer as Cloud signer
    participant Recipient as Recipient
    Owner->>API: POST /shares
    API->>API: Authenticate + authorize object
    API->>DB: Save grant (token hash, scope, expiry)
    API-->>Owner: Share link
    Recipient->>API: GET /shares/{token}
    API->>DB: Validate expiry, revoke, recipient, usage
    API->>Signer: Sign exact object/method for short TTL
    Signer-->>API: Short-lived signed URL
    API-->>Recipient: Redirect or stream
~~~

Do not store full cloud URLs in the database unnecessarily. Signed URLs are credentials; persisting them widens the leak surface. Store grant IDs, resources, permissions, expiry, signer references, and audit metadata.

### 5.2. Suggested schema

~~~sql
CREATE TABLE share_grant (
    id UUID PRIMARY KEY,
    token_hash BYTEA NOT NULL UNIQUE,
    tenant_id UUID NOT NULL,
    resource_type VARCHAR(40) NOT NULL,
    resource_id UUID NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    permission VARCHAR(16) NOT NULL,
    recipient_hash BYTEA,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    max_uses INTEGER,
    use_count INTEGER NOT NULL DEFAULT 0,
    require_recipient_auth BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

This schema is illustrative. Audit events can live in a separate table; never store raw tokens, signed URLs, OTPs, or access tokens. The token hash is computed from a high-entropy random token, not a weak password hash.

### 5.3. Generating cryptographically secure random tokens

Use a CSPRNG to generate high-entropy tokens, such as 32 random bytes encoded as URL-safe Base64:

~~~java
@Component
public class ShareTokenGenerator {
    private final SecureRandom secureRandom = new SecureRandom();

    public String generate() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

32 bytes equals 256 bits of entropy before encoding. Avoid using UUID v4 as a secret token when maximum entropy is desired; UUIDs are fine as public IDs, kept separate from secret tokens.

Hash the token for storage:

~~~java
public byte[] sha256(String token) throws GeneralSecurityException {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    return digest.digest(token.getBytes(StandardCharsets.US_ASCII));
}
~~~

Because the random token already has high entropy, SHA-256 is appropriate for hash lookups without needing a slow password KDF. For human-chosen passwords, always use dedicated password hashing; never apply this pattern to passwords.

### 5.4. Validating grants on the server

On every access, verify:

- The token matches and has not expired.
- The grant has not been revoked.
- The resource still exists and the owner/tenant remains valid.
- The permission matches the request.
- The recipient is authenticated if required by the grant.
- Usage quota has not been exceeded.
- Resource classification permits external sharing.
- No legal hold or business state blocks downloads.

Do not check permissions only once at link creation time. Owner privileges or document status may change before the recipient uses the link.

### 5.5. Atomic one-time use

If the application requires single-use links, state updates must be atomic. Example SQL:

~~~sql
UPDATE share_grant
SET use_count = use_count + 1
WHERE token_hash = :tokenHash
  AND revoked_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
  AND (max_uses IS NULL OR use_count < max_uses)
RETURNING id, tenant_id, resource_id, object_key, permission;
~~~

Within a transaction, only the request whose update succeeds is allowed to proceed. Never read `use_count`, check it in Java, and update separately—two concurrent requests could both pass the check.

**Note:** if the server redirects the recipient to a presigned URL valid for 10 minutes, the recipient can reuse that cloud URL multiple times during those 10 minutes. Consuming the application token once does not turn the signed URL into a one-time URL. If strict one-time access is required, the backend must proxy/stream the content and enforce every request, or use a storage mechanism with supported one-time semantics.

### 5.6. Grant lifetime vs. signed URL lifetime

There are two timestamps:

- When the application share link expires.
- When the direct cloud URL expires.

When generating a signed URL, set the expiry to the lesser of the configured TTL and the grant's remaining lifetime:

~~~java
Instant signedExpiry = min(
        clock.instant().plus(configuredSignedUrlTtl),
        grant.expiresAt());
~~~

Never issue a signed URL outliving the underlying grant. If a recipient already received a signed URL and the grant is subsequently revoked, the direct URL may keep working until expiry unless the provider supports explicit revocation; therefore, use very short TTLs or proxy downloads when instant revocation is required.

## 6. Generating AWS S3 Presigned URLs

### 6.1. Mechanism

An S3 presigned URL signs a request covering bucket, object key, HTTP method, expiration, and signed request components. The URL's authority is bounded by the signing IAM principal's permissions and applicable bucket/access point policies.

- Recipients need no AWS credentials.
- The URL can be reused until it expires.
- The URL cannot exceed the signing principal's permissions.
- With temporary credentials, the URL stops working when those credentials expire, even if a longer expiry was requested.
- AWS SDK/CLI SigV4 permits up to 7 days; never use that as a default.

### 6.2. Spring Boot with AWS SDK for Java 2.x

Example creating a `GET` URL for an object:

~~~java
@Service
public class S3ShareUrlService {
    private final S3Presigner presigner;

    public S3ShareUrlService(S3Presigner presigner) {
        this.presigner = presigner;
    }

    public URL createDownloadUrl(String bucket, String objectKey) {
        Duration ttl = Duration.ofMinutes(10);

        GetObjectRequest getRequest = GetObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .responseContentDisposition("attachment")
                .build();

        GetObjectPresignRequest presignRequest =
                GetObjectPresignRequest.builder()
                        .signatureDuration(ttl)
                        .getObjectRequest(getRequest)
                        .build();

        return presigner.presignGetObject(presignRequest).url();
    }
}
~~~

This snippet requires the AWS SDK S3 dependency and appropriate presigner module. `S3Presigner` should be configured using the default credential provider chain so the workload uses IAM roles/temporary credentials; never embed access keys in source code.

### 6.3. Presigned PUT and uploads

Example signing a `PUT`:

~~~java
PutObjectRequest putRequest = PutObjectRequest.builder()
        .bucket(bucket)
        .key(serverGeneratedObjectKey)
        .contentType("application/pdf")
        .build();

PutObjectPresignRequest presignRequest =
        PutObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(10))
                .putObjectRequest(putRequest)
                .build();

PresignedPutObjectRequest signed =
        presigner.presignPutObject(presignRequest);

URL uploadUrl = signed.url();
Map<String, List<String>> requiredHeaders = signed.signedHeaders();
~~~

The client must send the exact HTTP method and signed headers returned by the signer. Never sign permissions to list buckets or delete objects when only uploading a single file. For large uploads or strict size/content-type policies, evaluate S3 presigned `POST` policies or an upload proxy.

### 6.4. Tightening signature age and revocation

You can use a bucket policy with the `s3:signatureAge` condition key to reject presigned requests whose signatures are older than a threshold, such as 10 minutes:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOldPresignedRequests",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::example-bucket/shared/*",
      "Condition": {
        "NumericGreaterThan": {
          "s3:signatureAge": 600000
        }
      }
    }
  ]
}
~~~

The value is in milliseconds. This policy serves as a bucket/access-point guardrail; test the resource scope and application impact carefully. It can reject URLs earlier than the query-string expiry, though it never extends a URL's lifetime.

There is no API to revoke a single presigned URL individually. Broader blocking measures include:

- Disabling/revoking the credentials or session that signed the URL.
- Updating IAM/bucket policies to deny the resource or request.
- Deleting/moving the object or changing access permissions.
- Enforcing `s3:signatureAge` to cap signature age.

These measures can affect multiple URLs or workloads sharing the same credentials/policy. Designing short-lived links and re-issuing as needed is usually easier to operate.

### 6.5. Limitations and auditing

- Never send URLs to logs or chat.
- Grant the signer role access only to required buckets/prefixes.
- Requests can be audited and the signing IAM principal/role session identified through appropriate logs.
- For uploads, objects at the same key can be overwritten; use a fresh key per upload and inspect objects afterward.
- Downloads started before expiry may continue; retries after expiry may fail.
- Presigned URLs remain subject to applied network/IP/VPC endpoint policies.

## 7. Generating Azure Storage SAS

### 7.1. Choosing the right SAS type

Azure Storage provides three primary types:

| Type | Signing mechanism | Scope |
| --- | --- | --- |
| User delegation SAS | User delegation key backed by Microsoft Entra credentials | Supported resources; recommended for Blob Storage |
| Service SAS | Storage account key | A single storage service/resource |
| Account SAS | Storage account key | One or more storage services and certain service-level operations |

Microsoft recommends **user delegation SAS** for most Blob Storage scenarios because it relies on Microsoft Entra credentials instead of account keys. Restrict permissions on the SAS creator and avoid issuing broad account SAS tokens when only one blob is needed.

### 7.2. Generating a user delegation SAS in Java

Conceptual example with the Azure Storage Blob SDK:

~~~java
BlobServiceClient blobServiceClient = new BlobServiceClientBuilder()
        .endpoint(storageEndpoint)
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

Instant now = Instant.now();
OffsetDateTime startsOn = OffsetDateTime.ofInstant(
        now.minus(Duration.ofMinutes(5)), ZoneOffset.UTC);
OffsetDateTime expiresOn = OffsetDateTime.ofInstant(
        now.plus(Duration.ofMinutes(10)), ZoneOffset.UTC);

UserDelegationKey delegationKey =
        blobServiceClient.getUserDelegationKey(startsOn, expiresOn);

BlobSasPermission permission = new BlobSasPermission()
        .setReadPermission(true);

BlobServiceSasSignatureValues values =
        new BlobServiceSasSignatureValues(expiresOn, permission)
                .setStartTime(startsOn)
                .setProtocol(SasProtocol.HTTPS_ONLY);

BlobClient blobClient = blobServiceClient
        .getBlobContainerClient(containerName)
        .getBlobClient(blobName);

String sas = blobClient.generateUserDelegationSas(
        values, delegationKey);

URI shareUri = URI.create(blobClient.getBlobUrl() + "?" + sas);
~~~

Constructor/method names may vary slightly across Azure Storage SDK for Java versions; align dependencies with the Azure SDK BOM. The identity creating the delegation key needs appropriate data-plane permissions to obtain a user delegation key and generate the SAS. Recipients using the SAS do not need the application's Entra token.

### 7.3. Grant only required permissions and resources

SAS permissions include flags such as read, add, create, write, delete, and list depending on resource type. For a blob download link, grant only read. Never grant write/delete/list unless the use case requires it.

- Scope strictly to the target blob/container.
- Enforce `HTTPS_ONLY` protocol.
- Set a short expiry.
- Use IP ranges when recipients have stable addresses and policy requires it.
- Never grant broad permissions on an account SAS.
- Prefer user delegation SAS over account-key SAS whenever applicable.

### 7.4. Expiration policies and revocation

A storage account can configure a SAS expiration policy to recommend or block SAS tokens exceeding an allowed duration. Two actions exist:

- **Log:** allows requests while logging out-of-policy SAS tokens when diagnostic logging is configured.
- **Block:** rejects out-of-policy requests.

User delegation SAS has a maximum lifetime of 7 days; the user delegation key has its own expiry, and if the key expires, any SAS signed with it becomes invalid. Stored access policies are not supported for user delegation SAS or account SAS.

For a service SAS linked to a stored access policy, you can revoke it by deleting or modifying the referenced policy. An ad hoc service SAS without a policy can usually only be revoked immediately by regenerating the signing account key, which impacts other workloads using that key. User delegation SAS has no stored access policy; revocation relies on revoking/disabling the user delegation key/identity and blocking the resource.

**Do not assume every SAS type has the same revocation mechanism.** Document the SAS type, signing key/policy reference, and planned revocation procedure in your design.

### 7.5. Safe operations

- Enable Azure Storage diagnostic logs to investigate SAS-authenticated requests.
- Restrict permissions to generate SAS tokens; SAS generation does not always produce a standalone audit event as easily traceable as normal API calls.
- Consider disabling Shared Key authorization if workloads no longer need service/account SAS.
- Never store SAS query strings in application logs.
- If a SAS leaks, identify its type and signing key/policy to select the right revocation action.
- Use Entra ID/Managed Identity for server-to-server applications; issue SAS only for delegated external client access.

## 8. Generating Google Cloud Storage Signed URLs

### 8.1. Mechanism

A GCS signed URL contains a signature and query parameters identifying the credential, timestamps, method/headers, and object. Anyone with the URL can make the request during its validity window without needing a Google account.

Key points to remember:

- V4 signed URLs have a maximum lifetime of 604800 seconds (7 days).
- Signed URLs only access Cloud Storage through XML API endpoints.
- The signer must possess sufficient permissions for the operation.
- URLs can become invalid early if the signing key is rotated or the underlying identity/permissions change.
- Signed headers must be sent accurately when using the URL.

### 8.2. Generating signed URLs with the Java client

`GET` example:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();

BlobInfo blobInfo = BlobInfo.newBuilder(bucketName, objectName).build();

URL signedUrl = storage.signUrl(
        blobInfo,
        10,
        TimeUnit.MINUTES,
        Storage.SignUrlOption.withV4Signature(),
        Storage.SignUrlOption.httpMethod(HttpMethod.GET));
~~~

This illustrates the Cloud Storage Java client API. The runtime environment needs a suitable signer, typically a service account identity authorized to sign via the IAM Credentials API or an organization-approved key mechanism. Avoid storing service account JSON private keys inside containers.

### 8.3. Signed upload URLs

For uploads, specify `PUT` and bind `Content-Type`/headers where supported by the client library:

~~~java
URL uploadUrl = storage.signUrl(
        blobInfo,
        10,
        TimeUnit.MINUTES,
        Storage.SignUrlOption.withV4Signature(),
        Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
        Storage.SignUrlOption.withContentType());
~~~

The client must send the exact signed `Content-Type`. Additional signed headers may be needed for checksums or preconditions. Verify the object after upload, enforce size/content-type checks in a validation pipeline, or use a signed policy document when more flexible upload policies are needed.

### 8.4. Revocation and key rotation

GCS signed URLs have no per-URL revoke operation. Ways to cut off access include:

- Waiting for the URL to expire.
- Rotating/revoking the relevant signing key or service account key.
- Modifying signer permissions or object access permissions.
- Deleting/moving the object or applying a blocking policy.

These actions are coarse-grained and may break other signed URLs. When instant per-share revocation is required, use an application share link/proxy that checks the grant before each download.

## 9. OAuth Access Tokens and Shared Tokens

### 9.1. Access tokens must have scope and audience

Access tokens must constrain:

- Trusted issuer.
- Represented subject/client.
- Audience identifying the resource server permitted to accept the token.
- Expiration and not-before timestamps.
- Permitted scopes/permissions.
- Token ID if tracking/revocation is needed per architecture.

Never trust claims merely because a token is a JWT. The resource server must validate signature, issuer, audience, timestamps, and algorithm against trusted configuration. For opaque tokens, the resource server can introspect with the authorization server.

### 9.2. Send bearer tokens in the Authorization header

Correct:

~~~http
GET /api/documents/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Avoid:

~~~text
https://api.example.com/documents/123?access_token=...
~~~

Tokens in query strings easily end up in browser history, proxy/access logs, analytics, copied links, and `Referer` headers. URL query strings may also be recorded by observability tools even over HTTPS.

### 9.3. Spring Security Resource Server

Example JWT resource server configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Protecting an endpoint:

~~~java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_document:read')")
    public DocumentView get(@PathVariable UUID id) {
        return documentService.readAuthorized(id);
    }
}
~~~

Authority mapping depends on claims and the configured converter. `issuer-uri` alone does not guarantee proper scope mapping; verify audience and API permissions per system policy. Never reuse the same access token across unrelated audiences.

### 9.4. Refresh tokens

Refresh tokens generally live longer than access tokens and can mint new access tokens. Therefore:

- Store refresh tokens securely on the client; for browsers, consider Backend-for-Frontend with `HttpOnly`/`Secure`/`SameSite` cookies based on your threat model.
- Use rotation/one-time use when supported by the authorization server.
- Detect reuse and revoke the token family per provider mechanisms.
- Never put refresh tokens in URLs, logs, or analytics.
- Revoke on logout, password change, suspected compromise, or session end per policy.

## 10. Revocation and Handling Leaked Links/Tokens

### 10.1. Revocation matrix

| Type | Revoke a specific link | Practical measures |
| --- | --- | --- |
| Application share token | Yes | Mark grant revoked; all subsequent requests are rejected by the app |
| AWS S3 presigned URL | Not directly | Revoke signing credentials/session, deny via bucket policy, block object, or restrict signature age |
| Azure service SAS with stored access policy | Possible via policy | Delete/replace stored access policy; check other SAS tokens sharing that policy |
| Azure ad hoc service/account SAS | Not directly | Regenerate signing account key or block resource; may impact multiple workloads |
| Azure user delegation SAS | No stored policy | Revoke/disable delegation key or identity where possible, block resource, wait for expiry |
| GCS signed URL | Not directly | Rotate signing key/identity or block object/resource, wait for expiry |
| OAuth opaque token | Possible if introspection/revocation supported | Revoke at the authorization server |
| Self-contained JWT | No built-in instant revocation | Short TTL, token ID denylist, token versioning, or introspection/gateway policy |

### 10.2. Incident response

When a link is suspected of leaking:

1. Identify the credential type: application token, S3 URL, SAS, GCS URL, or OAuth token.
2. Identify the resource, method, expiry, signer, tenant, and intended recipient.
3. Revoke the grant at the application layer if applicable.
4. Trigger the appropriate provider revocation/policy/resource control.
5. If necessary, temporarily block the object/prefix or pause the share API.
6. Inspect access logs, IPs, user agents, timestamps, download counts, and anomalous requests.
7. Assess what data was already downloaded; revoking a URL does not delete copies already fetched.
8. Rotate credentials/keys if compromise is possible.
9. Issue a new link with narrower scope/TTL after verifying owner and recipient.
10. Document the incident, root cause, and guardrail improvements.

Never claim that data already downloaded has been "revoked." Revoking a link only blocks future access via provider/app controls.

### 10.3. Per-grant revocation via proxy

When immediate per-share revocation is required, route every request through the share service:

~~~text
GET https://share.example.com/s/{opaque-token}
             |
             v
Check grant status + recipient + expiry
             |
             +---- revoked/expired -> 404/410
             |
             +---- allowed -> stream from storage
~~~

Proxying maintains control on every request, at the expense of bandwidth, latency, and backend load. A gateway/CDN with an authorization callback can help if supported. If the proxy merely redirects to a signed URL, that cloud URL remains reusable until expiry; do not treat redirects as instant revocation.

## 11. Protecting URLs and Tokens from Leakage

### 11.1. Never log full URLs

Signed URLs contain signatures and query credentials. Application share tokens in paths are also credentials; never write full URLs, raw tokens, or full request targets into:

- Application logs.
- Reverse proxy/access logs.
- APM/tracing spans.
- Analytics events.
- Error reports.
- Support tickets or chat.
- Audit events.

Use safe metadata instead:

~~~json
{
  "event": "share_url_issued",
  "shareId": "sh_8a7f...",
  "resourceRef": "doc_204",
  "permission": "READ",
  "expiresAt": "2026-11-24T10:30:00Z",
  "actorRef": "user_91"
}
~~~

Do not log token hashes unnecessarily; token hashes remain sensitive and can aid correlation or offline guessing if token entropy is weak. Use opaque grant IDs in audits.

### 11.2. Browsers and Referer

If a page displays a signed URL or redirects to a shared resource:

- Use HTTPS.
- Set `Referrer-Policy` to `no-referrer` on sharing pages.
- Avoid loading third-party analytics, fonts, images, or scripts on pages whose URLs hold tokens.
- Never embed signed URLs in HTML that could be publicly cached.
- Set `Cache-Control` to `no-store` for pages issuing links and responses containing credentials.
- Prevent URLs from appearing in client-side error telemetry.
- Strip query strings from access logs or redact signature parameters.

`Referrer-Policy` reduces URL leakage via `Referer`, but does not clear browser history or prevent users from copying links. Tokens must still have short TTLs and narrow scopes.

### 11.3. Email, chat, and clipboard

- Send links only over recipient-verified channels.
- Avoid posting links in mailing lists or public tickets.
- Never put URLs in email subject lines.
- For sensitive links, send a separate notification and require recipient sign-in/OTP.
- Never log clipboard contents or URLs in telemetry.
- Consider sending application share links instead of cloud signed URLs so recipients can be verified and links revoked.

### 11.4. CORS is not authorization

CORS governs which browser JavaScript origins can read responses. CORS does not prevent someone from copying a signed URL into `curl`, another browser, or a server. Never rely on CORS as a revocation or holder-verification mechanism.

## 12. Testing and Observability

### 12.1. Time boundary test matrix

| Test | Expected result |
| --- | --- |
| Request before start time | Rejected |
| Request within TTL | Succeeds if all policies allow |
| Request right after expiry | Rejected |
| Temporary credentials expire before URL | Rejected once credentials expire |
| URL revoked / policy denies | New requests rejected |
| Download started near expiry | Behavior follows provider; retries after expiry must be tested separately |
| Clock skew | Tests catch unexpected start/expiry boundary behavior |

Inject `Clock` into Spring services so time-dependent behavior can be tested without real waiting.

### 12.2. Scope and permission tests

- A `GET` link cannot perform `PUT`/`DELETE`.
- A link for object A cannot access object B.
- A link for tenant A cannot access tenant B.
- A read link cannot list containers/buckets.
- An upload link cannot overwrite a different object.
- Wrong signed headers/`Content-Type` are rejected.
- Users without owner privileges cannot create shares.
- Wrong recipients are rejected by the app when grants bind recipients.

### 12.3. Replay and one-time tests

- Call the same signed URL multiple times to confirm provider behavior (typically reusable).
- Invoke an application one-time token concurrently from two requests; only one request may consume it.
- If the app redirects to a signed URL, test that the target URL remains replayable until expiry.
- If true one-time access is required, verify the proxy streams from storage without returning raw credentials.

### 12.4. Revocation tests

- Revoke an application grant and retry the link.
- Delete a service SAS stored access policy and verify access stops.
- Test an `s3:signatureAge` bucket policy against an older URL.
- Test disabling signer credentials in a test environment.
- Test GCS signing key rotation on a test bucket.
- Verify coarse-grained revocation controls do not disrupt unrelated workloads.

### 12.5. Audits and metrics

Track:

- Number of share links created by actor, tenant, and resource classification.
- Average TTL and count of links exceeding policy.
- Successful/failed accesses, IPs, and user agents per privacy policy.
- Counts of revocations, expirations, and recipient verification failures.
- Uploads rejected for size/type/checksum violations.
- Access attempts after revocation or expiry.
- Anomalous requests across many IPs/regions or high rates.

Never include raw URLs, SAS tokens, signatures, bearer tokens, or sensitive plaintext object metadata in metrics/logs.

## 13. Troubleshooting Common Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Newly created URL returns 403 immediately | Signer credentials expired, start time/clock skew, or missing permissions | Check signer identity, UTC time, policies, and resource |
| URL expires earlier than configured | Temporary credentials/session expired first | Use appropriate session duration or shorter URL TTL |
| S3 URL rejected after a few minutes | `s3:signatureAge` bucket policy or network policy | Check guardrail policies and signer |
| S3 `GET` URL works multiple times | Normal presigned URL behavior | Use an application proxy if one-time access is needed |
| Azure SAS cannot be revoked via stored policy | May be user delegation SAS/account SAS or SAS without a policy | Identify SAS type and use the proper revocation mechanism |
| Azure SAS expired while delegation key is still valid | SAS expiry and user delegation key expiry are separate timestamps | Check both timestamps and account policies |
| GCS signed URL returns 403 | Signer lacks permissions, wrong signed header, expired, or wrong endpoint | Check identity, canonical request, XML API, and expiry |
| OAuth API receives token in query string | Client is passing tokens incorrectly | Move token to `Authorization` header |
| Link leaked in logs | Query strings logged verbatim | Redact in app/proxy/APM before persistence |
| Link still usable after owner revokes | Direct signed URL remains valid until expiry | Proxy downloads or revoke provider credentials/policy/resource |
| One-time link can still be downloaded again | App redirects to a reusable signed URL | Proxy/stream content and consume the grant per request |
| Recipient cannot open link | TTL too short, slow network, or missing required headers | Tune TTL, supply headers, and offer a safe re-issue flow |

## 14. Comprehensive Hands-On Exercise

**document-service** lets document owners share PDF contracts with partners for 10 minutes. Recipients have no cloud identity. Document owners can revoke links immediately. Certain Restricted documents must require an OTP before download.

**Tasks:**

1. Design a `share_grant` table storing token hashes, tenant, resource, permission, expiry, recipient, and revocation state.
2. Generate 256-bit random tokens and store only their SHA-256 hashes.
3. Verify owner permissions and data classification before creating a share.
4. Pick a cloud provider and generate a signed `GET` URL scoped to a single object with a short TTL.
5. Explain revocation limitations of presigned URLs/SAS/signed URLs for that provider.
6. Design a download proxy to revoke individual grants and enforce one-time use when needed.
7. Add OTP/login verification for Restricted documents.
8. Protect URLs from logs, traces, browser referrers, analytics, and tickets.
9. Write tests for expiry, wrong HTTP method, wrong object, replay, revocation, and concurrent one-time consumption.
10. Draft an incident runbook for links forwarded externally.

**Self-assessment questions:**

- Why is a signed URL considered a bearer credential?
- Is an S3 presigned URL automatically single-use?
- Why can temporary AWS credentials cause a URL to expire before its configured expiry?
- How does an Azure user delegation SAS differ from a service SAS?
- Do stored access policies apply to every SAS type?
- What is the maximum lifetime of a GCS V4 signed URL and which API endpoint does it use?
- Why must OAuth access tokens never be placed in query strings?
- When redirecting to a signed URL, does an application one-time token guarantee one-time download?
- Can CORS stop someone from using a copied URL?
- When immediate per-link revocation is required, what architecture fits best?
- Why is it impossible to revoke data that a recipient has already downloaded?

**Guided answers:** whoever holds the link can exercise the signed permissions; S3 presigned URLs are reusable until expiry; temporary credentials have their own expiration; user delegation SAS uses Entra credentials whereas service SAS uses an account key; stored access policies only support service SAS; GCS V4 lasts at most 604800 seconds and uses the Cloud Storage XML API only; bearer tokens belong in the `Authorization` header; redirects still expose a reusable cloud URL; CORS is not authorization; a proxy/application grant checking every request enables per-link revocation; already-downloaded bytes are outside the link's control.

## 15. Official References

- [AWS S3 – Download and upload objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html): signer permissions, expiration, temporary credentials, replay, and URL limits.
- [AWS – Additional guardrails for presigned URLs](https://docs.aws.amazon.com/prescriptive-guidance/latest/presigned-url-best-practices/additional-guardrails.html): using `s3:signatureAge` to tighten signature age and guardrail bounds.
- [Azure Storage – Grant limited access with SAS](https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview): user delegation/service/account SAS, permissions, and stored access policies.
- [Azure Storage – SAS expiration policy](https://learn.microsoft.com/en-us/azure/storage/common/sas-expiration-policy): SAS duration limits, Log/Block actions, and user delegation keys.
- [Azure Storage REST – Create a service SAS](https://learn.microsoft.com/en-us/rest/api/storageservices/create-service-sas): lifetimes and revoking SAS via stored access policies/account keys.
- [Google Cloud Storage – Signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls): bearer behavior, XML API, expiry, and signers.
- [Google Cloud – Create signatures](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures): signing identities and key rotation.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): transmitting bearer tokens in the `Authorization` header, TLS, and keeping tokens out of URLs.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token protection, audience, sender constraints, and refresh tokens.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer configuration, JWT validation, and authority mapping.

**Remember:** a secure share link requires **a short TTL, a specific resource, minimal methods/permissions, a tightly scoped signer, and a revocation plan**. Direct signed URLs are typically replayable bearer links; when you need recipient verification, per-link revocation, or one-time use, have Spring Boot validate the grant on every request and grant storage access only for the briefest window needed.

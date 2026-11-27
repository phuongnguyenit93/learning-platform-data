# Signed URLs and Permissions of the Signing Identity

## 1. The Problem of Time-Limited Object Sharing

A Spring Boot application may store documents, images, report exports, or user files in Google Cloud Storage (GCS). When a user needs to download a file, the backend usually does not want to download all the bytes through itself and proxy them onward. Likewise, when a user uploads, the backend does not necessarily have to receive the file and forward it to the bucket. A **Signed URL** allows the backend to issue a cryptographically signed URL scoped to an object, HTTP method, and expiration time; the client can exchange data directly with Cloud Storage without needing a Google account or separate IAM credentials.

A signed URL does not make a bucket public. It creates temporary access for whoever holds the URL. Anyone with the URL can use it while it remains valid, provided the request matches the signed method, resource, query parameters, and headers. Therefore, a signed URL must be treated like a bearer credential.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on signed URLs, the V4 signing workflow, and IAM permissions of the signing identity.

After this lesson, you will be able to:

- Explain signed URLs, V4 signatures, and the bearer access model.
- Distinguish between the signing principal, the signer service account, and the URL consumer.
- Grant the proper `iam.serviceAccounts.signBlob` permission and object permissions to the signer.
- Generate GET/PUT signed URLs with the Java Cloud Storage client.
- Use service account impersonation to sign without issuing long-lived private keys.
- Constrain HTTP method, Content-Type, query parameters, generation, and expiration.
- Integrate signed URLs into a Spring Boot flow with business authorization checks.
- Protect URLs, configure CORS, and handle signature/permission/expiration errors.

> **Version scope:** Examples use the Google Cloud Storage Java client, V4 signing, and the Google Auth Library. Overloads, packages, and dependency versions must be aligned via your project's BOM; check the Javadoc for the exact resolved version. This lesson prioritizes service account impersonation and the IAM Credentials API, without requiring service account private keys in source code or container images.

## 2. What Is a Signed URL?

A signed URL is a URL containing authentication information in its query string. The signature allows Cloud Storage to verify that the request is executed under the authority of a specific account, even when the requester has no Google Cloud credentials.

A signed URL typically binds:

- **Resource:** a specific bucket/object.
- **HTTP method:** e.g., `GET` for reading or `PUT` for uploading.
- **Expiration:** the timestamp when the URL expires.
- **Signed headers:** headers that must match, such as `Content-Type`.
- **Query parameters:** parameters included in the canonical request and protected by the signature.

For example, a V4 URL includes query parameters such as `X-Goog-Algorithm`, `X-Goog-Credential`, `X-Goog-Date`, `X-Goog-Expires`, `X-Goog-SignedHeaders`, and `X-Goog-Signature`. The Java client generates these fields automatically; the application should not append or modify the URL after signing.

~~~mermaid
sequenceDiagram
    participant User as User
    participant API as Spring Boot API
    participant IAM as IAM Credentials API
    participant GCS as Cloud Storage

    User->>API: Request document download URL
    API->>API: Authenticate user and check document permissions
    API->>IAM: Sign request as service account
    IAM-->>API: Signature
    API-->>User: Time-limited Signed URL
    User->>GCS: GET object using signed URL
    GCS->>GCS: Verify signature, method, headers, expiry
    GCS-->>User: Object bytes
~~~

The user does not need direct IAM permissions on the bucket. Cloud Storage authenticates the request via the signature and enforces the permissions of the identity that signed the URL.

### 2.1. A Signed URL Is Not a Public Object

| Access method | Who can access? | Condition |
| --- | --- | --- |
| Public object | Everyone per public policy | Bucket/object granted public access |
| IAM authenticated access | Principal with IAM permissions | Request carries valid credentials |
| Signed URL | Anyone holding the URL | URL is unexpired and request matches signature |
| `gs://bucket/object` | Grants no permissions by itself | Caller still needs credentials and IAM |

A signed URL provides temporary access to the signed resource. Once expired, the URL can no longer be used; the object retains the bucket's normal IAM policy.

### 2.2. When Do Signed URLs Fit?

- The backend verifies user permissions and issues a URL to download a single file.
- A user uploads a file directly to an object path determined by the backend.
- The application needs to transfer large payloads directly between the client and Cloud Storage.
- An external service needs short-lived access to a specific object without being granted Google credentials.

Signed URLs are usually unnecessary for copy, compose, bucket listing, metadata edits, or deletions performed by the backend. In those cases, the backend can call the Storage API directly under its own workload identity.

## 3. V4 Signing and What It Protects

### 3.1. Why Prefer V4?

Cloud Storage supports multiple signing versions. For new applications, use **V4 signing** and explicitly specify `withV4Signature()` to avoid relying on library version defaults.

V4 uses the `GOOG4-RSA-SHA256` algorithm when signing with a service account RSA key. The canonicalization and signing steps include:

1. Determine HTTP method and canonical resource path.
2. Canonicalize signed headers.
3. Canonicalize query parameters.
4. Build the canonical request.
5. Build the string-to-sign containing timestamp, credential scope, and hash of the canonical request.
6. Sign the string-to-sign using the signer identity.
7. Include the signature in the `X-Goog-Signature` query parameter.

The Google Cloud library performs these steps. Implement canonical requests manually only when there is a special requirement and thorough testing; a tiny difference in encoding, whitespace, headers, or query parameter ordering invalidates the signature.

### 3.2. Method, Headers, and Query Parameters Must Match

If a URL is signed for `GET`, the client cannot change it to `PUT`. If the signature requires `Content-Type: application/pdf`, the upload request must send the exact signed value. If an unsigned query parameter is added, the V4 request may be rejected.

| Component | Example | Behavior |
| --- | --- | --- |
| HTTP method | `GET`, `PUT` | Must use the exact signed method |
| Object path | `/bucket/reports/a.pdf` | Object name cannot be changed |
| Content-Type | `application/pdf` | Must match signed header |
| Query parameter | `ifGenerationMatch=0` | Must be included in the signature |
| Expiration | 15 minutes | Request must arrive within validity window |
| Host | `storage.googleapis.com` | Required header in signed headers |

Do not alter the URL by appending query parameters, changing the host arbitrarily, or re-encoding the path after signing.

### 3.3. Endpoint Scope

Cloud Storage signed URLs are used only to access resources via **XML API endpoints**. Do not use them as `gs://` URIs, JSON API URLs, or console URLs. Clients typically send requests to the host generated in the signed URL, such as `storage.googleapis.com`.

## 4. Three Identities to Distinguish

Three distinct roles participate in a signed URL flow:

1. **Signing principal:** the user or workload identity running Spring Boot and calling the IAM Credentials API to request a signature.
2. **Signer service account:** the service account chosen as the identity that executes the GCS request later; the URL is signed under this account's authority.
3. **URL consumer:** the browser, mobile app, or partner receiving the URL and sending requests to Cloud Storage.

~~~mermaid
flowchart TD
    SOURCE["Signing principal<br/>API runtime identity"] -->|"iam.serviceAccounts.signBlob"| SIGNER["Signer service account"]
    SIGNER -->|"storage.objects.get / create / delete"| OBJECT["Bucket / object"]
    CONSUMER["URL consumer<br/>Browser / mobile / partner"] -->|"URL + signed method"| GCS["Cloud Storage"]
    SIGNER -. "Identity in signature" .-> GCS
~~~

**The signing principal is not automatically the signer.** For example, a Cloud Run service running as `document-api-runtime@...` can impersonate `document-download-signer@...`. The runtime identity only needs permission to sign on behalf of that service account; the signer service account is the principal that needs permission to read objects.

The URL consumer needs no Google IAM role. The consumer's capabilities are constrained by the signed method, object, headers, query parameters, and expiration.

### 4.1. Signer Object Permissions

| Signed request | Signer permission | Common role |
| --- | --- | --- |
| GET object | `storage.objects.get` | `roles/storage.objectViewer` |
| HEAD/read metadata | `storage.objects.get` | `roles/storage.objectViewer` |
| PUT creating new object | `storage.objects.create` | `roles/storage.objectCreator` |
| PUT that may overwrite object | `storage.objects.create` and `storage.objects.delete` | `roles/storage.objectUser` or scoped custom role |
| DELETE object | `storage.objects.delete` | Role with appropriate delete permission |

Grant these roles at bucket scope if the signer serves only one bucket. Do not grant `roles/storage.admin` at project scope to a service that only issues document download URLs.

`roles/storage.objectCreator` does not implicitly allow reading, deleting, or overwriting existing objects. If a signed PUT may replace an old object, the signer also needs delete permission on the old object under Cloud Storage semantics. If only creating new objects, use unique object names and the `ifGenerationMatch=0` precondition.

### 4.2. Permission to Sign on Behalf of a Service Account

The signing principal needs the permission:

`iam.serviceAccounts.signBlob`

This permission is included in the role:

`roles/iam.serviceAccountTokenCreator`

Grant this role on the **target service account** to the specific runtime principal rather than broadly across the entire project unless necessary. The Token Creator role also includes other token/credential creation capabilities; organizations may use a custom role containing only the required permission if policy permits.

Additionally, the project must enable the **IAM Service Account Credentials API** (`iamcredentials.googleapis.com`). Enabling the API requires `serviceusage.services.enable`.

### 4.3. Summary Permission Matrix

| Component | Required permission | Do not confuse with |
| --- | --- | --- |
| Signing principal | `iam.serviceAccounts.signBlob` on signer SA | Object read permission |
| Signer service account | `storage.objects.get/create/delete` per signed method | Permission to impersonate itself |
| URL consumer | No Google IAM credentials needed | Access to arbitrary objects |
| IAM admin | Enable API and assign appropriate roles | Runtime permission |

If the signing principal is a service account running on Cloud Run/GKE/Compute Engine, it must be granted Token Creator on the signer SA. If using user ADC in local development, that user also needs this role on the signer SA.

## 5. Setting Up IAM with gcloud

Suppose there are two service accounts:

- `document-api-runtime@training-platform-dev.iam.gserviceaccount.com`: identity running Spring Boot.
- `document-download-signer@training-platform-dev.iam.gserviceaccount.com`: identity signing document download URLs.

Enable the IAM Credentials API:

~~~bash
gcloud services enable iamcredentials.googleapis.com \
  --project=training-platform-dev
~~~

Grant the runtime identity permission to sign on behalf of the signer service account:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  document-download-signer@training-platform-dev.iam.gserviceaccount.com \
  --member="serviceAccount:document-api-runtime@training-platform-dev.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
~~~

Grant object read permission to the signer on the bucket:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://training-documents-prod \
  --member="serviceAccount:document-download-signer@training-platform-dev.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

For signed uploads that only create new objects, you can grant `roles/storage.objectCreator` at bucket scope. If the URL permits overwrites, evaluate `roles/storage.objectUser` or a custom role containing both create and delete.

These commands only illustrate configuration. Replace project, bucket, and service account with real resources and review IAM policies before applying. Do not grant signer permissions across multiple buckets when the application only needs one bucket.

## 6. Using ADC and Impersonation to Sign Without Private Keys

### 6.1. Why Can Standard ADC Fail to Sign?

Java `Storage.signUrl(...)` requires a credential implementing `ServiceAccountSigner`. Common ADC types such as user credentials created by `gcloud auth application-default login` or credentials from the metadata server do not necessarily implement this interface directly.

Therefore, simply calling `StorageOptions.getDefaultInstance().getService()` followed by `signUrl()` can throw `IllegalStateException` if the credential cannot sign directly. You must provide an explicit signer or use a suitable credential.

Do not solve this error by defaulting to generating a JSON service account key and bundling it into a container. Instead, use **ImpersonatedCredentials** to ask the IAM Credentials API to sign on behalf of the target service account.

### 6.2. ImpersonatedCredentials

`ImpersonatedCredentials` allows source credentials to act on behalf of another service account. In the Google Auth Library for Java, this class implements `ServiceAccountSigner`, so it can be passed into `Storage.SignUrlOption.signWith(...)`.

Permission flow:

- The runtime's ADC authenticates to Google Cloud.
- The runtime principal holds `roles/iam.serviceAccountTokenCreator` on the signer service account.
- The IAM Credentials API performs the `signBlob` signing operation.
- The signed URL carries the identity of the signer service account.
- When the consumer uses the URL, Cloud Storage authorizes the request using the signer's permissions.

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.io.IOException;
import java.util.Collections;

public class SignedUrlCredentialsFactory {

    public ImpersonatedCredentials createDownloadSigner(
            String signerServiceAccountEmail) throws IOException {

        GoogleCredentials source =
                GoogleCredentials.getApplicationDefault()
                        .createScoped(Collections.singletonList(
                                "https://www.googleapis.com/auth/iam"));

        return ImpersonatedCredentials.create(
                source,
                signerServiceAccountEmail,
                null,
                Collections.singletonList(
                        "https://www.googleapis.com/auth/devstorage.read_only"),
                300);
    }

    public Storage createStorageClient() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

The example uses ADC as source credentials and creates an impersonated signer with Cloud Storage read-only scope. The IAM scope on source credentials is for the IAM Credentials API. OAuth scopes do not replace IAM roles: the signer service account must still have `storage.objects.get` on the bucket.

For uploads, create signer credentials with an appropriate read/write scope and grant the corresponding object creator/user IAM role. Do not use a single overly permissive signer if download signer and upload signer can be separated.

### 6.3. Securing and Operating Impersonation

- Do not store access tokens or impersonated credentials in a database.
- Do not log signatures, session tokens, or full signed URLs.
- Use short token lifetimes; e.g., `300` seconds in the factory.
- Grant Token Creator to the runtime principal on the exact target service account.
- Enable the IAM Credentials API in the appropriate project.
- Monitor `iam.serviceAccounts.signBlob` errors and IAM Credentials API quota.
- Locally, use user ADC granted impersonation rights on the signer by an admin; in production, use workload identity/runtime service accounts.

Impersonation does not reduce the signer's permissions. If the signer can read the entire bucket, any GET signed URL generated by that signer exercises that authority on the signed object. Therefore, the signer's permissions must be constrained to the minimum needed.

## 7. Generating a GET Signed URL in Java

### 7.1. Configuring the Signer and Storage Bean

You can create the signer once in the Spring ApplicationContext and inject it into services:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.io.IOException;
import java.util.Collections;

@Configuration(proxyBeanMethods = false)
public class SignedUrlConfiguration {

    @Bean
    ImpersonatedCredentials downloadSigner(
            @Value("${app.gcs.download-signer}") String signerEmail)
            throws IOException {

        GoogleCredentials source = GoogleCredentials.getApplicationDefault()
                .createScoped(Collections.singletonList(
                        "https://www.googleapis.com/auth/iam"));

        return ImpersonatedCredentials.create(
                source,
                signerEmail,
                null,
                Collections.singletonList(
                        "https://www.googleapis.com/auth/devstorage.read_only"),
                300);
    }

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Property:

~~~yaml
app:
  gcs:
    download-signer: document-download-signer@training-platform-dev.iam.gserviceaccount.com
~~~

If the Spring Framework on Google Cloud starter already creates a `Storage` bean, inject the existing bean instead of declaring a second one. The example illustrates one configuration approach; avoid duplicate beans when auto-configuration is active.

### 7.2. Generating the GET URL

~~~java
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class DocumentSignedUrlService {

    private final Storage storage;
    private final ImpersonatedCredentials downloadSigner;

    public DocumentSignedUrlService(
            Storage storage,
            ImpersonatedCredentials downloadSigner) {
        this.storage = storage;
        this.downloadSigner = downloadSigner;
    }

    public URL createDownloadUrl(
            String bucket,
            String objectName) {

        BlobInfo object = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
                .build();

        return storage.signUrl(
                object,
                15,
                TimeUnit.MINUTES,
                Storage.SignUrlOption.withV4Signature(),
                Storage.SignUrlOption.signWith(downloadSigner));
    }
}
~~~

`15 MINUTES` is an example short lifetime. Choose the expiration based on file size, network speed, and user experience. Do not default to issuing multi-day URLs if a download normally takes a few minutes.

### 7.3. Downloading a File with a Signed URL

The consumer does not need to send an OAuth token or service account key:

~~~bash
curl --fail --show-error \
  --output report.pdf \
  "SIGNED_URL_FROM_API"
~~~

Do not send this URL to logs, analytics, or public tickets. If the API returns the URL in JSON, the frontend should hold it in memory while in use and avoid persisting it in local storage unless necessary.

## 8. Generating a PUT Signed URL for Uploads

### 8.1. Constraining Content-Type

For signed PUTs, the backend should determine the object name and Content-Type in advance. The `Content-Type` header can be included in the signature so the client cannot arbitrarily change it after the URL is issued.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public URL createUploadUrl(
        Storage storage,
        com.google.auth.oauth2.ImpersonatedCredentials signer,
        String bucket,
        String objectName) {

    BlobInfo object = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("application/pdf")
            .build();

    Map<String, String> signedHeaders =
            Map.of("Content-Type", "application/pdf");

    return storage.signUrl(
            object,
            15,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withExtHeaders(signedHeaders),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

The consumer must send the exact signed header:

~~~bash
curl --fail --show-error \
  --request PUT \
  --header "Content-Type: application/pdf" \
  --upload-file ./report.pdf \
  "SIGNED_URL_FROM_API"
~~~

If Content-Type differs from the signed value, Cloud Storage may return a signature mismatch error. Do not rely solely on the `.pdf` extension; the backend still needs to verify the uploaded file's actual content afterward.

### 8.2. Preventing Unintended Object Overwrites

A signed PUT can overwrite an existing object if the signed request allows it and the signer holds the required permissions. For uploads creating new objects, use unique object names and also sign the query precondition `ifGenerationMatch=0`.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public URL createNewObjectOnlyUrl(
        Storage storage,
        com.google.auth.oauth2.ImpersonatedCredentials signer,
        String bucket,
        String objectName) {

    BlobInfo object = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("application/pdf")
            .build();

    return storage.signUrl(
            object,
            15,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withExtHeaders(
                    Map.of("Content-Type", "application/pdf")),
            Storage.SignUrlOption.withQueryParams(
                    Map.of("ifGenerationMatch", "0")),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

The precondition `ifGenerationMatch=0` requires that the object does not exist at upload time. If a live generation already exists, the request fails rather than overwriting. Query parameters must be signed; the consumer cannot add or remove parameters on its own.

### 8.3. Verifying the Object After Upload

The backend should not mark a document as complete simply because the browser received HTTP 200. After upload:

1. Look up the object by the issued bucket/object name.
2. Read generation, size, content type, and checksums.
3. Verify maximum allowed size and allowed file type.
4. Check tenant/document ownership and upload state.
5. Persist business metadata into the database.
6. Transition the document to ready status only after verification.

Signed URLs control storage access; they do not replace file validation or domain authorization.

## 9. Signed URLs with Generation and Query Parameters

If you want a GET URL to point to a specific generation, include generation in the resource and signed query parameters:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public URL createVersionDownloadUrl(
        Storage storage,
        com.google.auth.oauth2.ImpersonatedCredentials signer,
        String bucket,
        String objectName,
        long generation) {

    BlobInfo object = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName, generation))
            .build();

    return storage.signUrl(
            object,
            15,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.withQueryParams(
                    Map.of("generation", Long.toString(generation))),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

This is useful when versioning is enabled and the application must guarantee users download the exact approved version. If only the live object name is signed, the URL normally reads whichever version is live at request time.

You can also sign query parameters such as `response-content-disposition` so browsers download the file with a desired filename. Every query parameter must be included during signing; do not append them after the URL is generated.

## 10. Expiration, Key Rotation, and URL Revocation

### 10.1. V4 Limits

V4 `X-Goog-Expires` accepts lifetimes from 1 second up to a maximum of **604800 seconds (7 days)**. This is a protocol maximum, not a recommended default lifetime.

Short lifetimes reduce the window of abuse if a URL is leaked. Choose practical lifetimes based on data sensitivity and client behavior:

| Use case | Example starting lifetime |
| --- | --- |
| Small image or PDF preview | 5–15 minutes |
| Large file download | 15–60 minutes depending on speed and retries |
| Large file upload | 15–60 minutes or dedicated resumable flow |
| Partner-shared link | Shortest duration feasible for the business workflow |

These values are design suggestions; test against real file sizes and network conditions.

### 10.2. Signing with IAM signBlob

When signing via the IAM Credentials API `signBlob`, Google uses managed service account keys that are rotated periodically. For signatures with expirations longer than 12 hours, the URL may stop working earlier than its declared expiration due to key rotation. Therefore, signatures via `signBlob` are best suited for short-lived URLs.

Even though V4 allows up to 7 days, do not issue 7-day URLs via IAM `signBlob` assuming they are guaranteed to work for the full 7 days. If longer sharing is needed, consider another architecture and carefully evaluate key lifecycle without falling back to uncontrolled long-lived keys.

### 10.3. Revocation and Lifecycle

Signed URLs have no per-URL revocation mechanism like an application session record. Expiration is the primary control. Changing the signer's permissions, disabling/rotating keys, or modifying the object's state can affect issued URLs; exact impact depends on the signing mechanism and policies.

Therefore:

- Use short-lived URLs.
- Do not use signed URLs as long-lived login tokens.
- If per-user immediate revocation is required, check authorization in the backend before issuing URLs and keep lifetimes short enough.
- If per-download-session control is needed, consider proxying downloads through the backend or a session-aware gateway.
- Do not assume an individual URL can be revoked without affecting related credentials or resources.

## 11. Protecting Signed URLs

### 11.1. Treat the URL as a Secret

A signed URL contains a signature and authentication parameters in its query string. Anyone holding the URL can use it within its validity window. Do not:

- Write the full URL into application logs, access logs, or distributed traces.
- Send the URL to analytics events, crash reports, or ticketing systems.
- Embed the URL in public HTML/metadata.
- Persist the URL in a database long-term without a valid business reason.
- Transmit the URL over unencrypted channels.
- Share one tenant's URL with another tenant.

If logging is needed, log only the internal object ID, method, expiration, signer identity, request ID, and issuance outcome; redact the query string and signature.

### 11.2. Issue Only for Backend-Verified Objects

Never sign a URL for an arbitrary bucket/object name supplied by a client. The backend must:

1. Authenticate the user.
2. Load document metadata from the database.
3. Verify tenant ownership and read/write permissions.
4. Retrieve the bucket/object name from the trusted record.
5. Select the signer matching the operation.
6. Generate the URL with fixed method, headers, query params, and expiry.
7. Record an audit event without the URL.

If clients can influence object naming, map through business IDs and prefix allowlists; never concatenate arbitrary paths directly.

### 11.3. Signed URLs Can Be Reused

A signed URL is not a one-time token by default. A GET URL can be called multiple times before it expires. A signed PUT can also be replayed, and without a precondition it can overwrite the object under the signer's authority.

Use unique object names, `ifGenerationMatch=0`, short lifetimes, and business state checks to mitigate replays or unintended overwrites.

### 11.4. Sensitive Data and Caching

For sensitive documents, set appropriate object and response cache policies; consider `Cache-Control: private, no-store`. Do not assume every proxy/CDN handles signed URLs the way you expect. Verify cache keys, query string handling, and log redaction in your content delivery infrastructure.

## 12. CORS When Browsers Use Signed URLs

If a browser calls Cloud Storage directly from a different origin, the browser enforces CORS. The bucket needs a CORS rule matching the origin, method, and request headers:

- Origin: specific frontend domain, e.g., `https://app.example.com`.
- Method: `GET` and/or `PUT`.
- Request headers: `Content-Type` and any signed headers sent by the browser.
- Response headers: headers the frontend needs to read, such as `ETag` or `Content-Range`.
- Max age: preflight cache duration per policy.

CORS is a browser mechanism controlling cross-origin responses. It does not grant IAM permissions and does not replace signatures. A signed URL can work with `curl` without CORS; browsers can still block it if CORS is not configured.

Do not use wildcard origins in production when the frontend has a fixed domain and handles sensitive data. Inspect `OPTIONS` preflight requests and actual headers sent by the browser.

## 13. Signed URLs and Resumable Uploads

Signed URLs usually fit a single GET or PUT request for an object. For large uploads needing recovery after interruptions, **resumable uploads** have their own session URI mechanism:

1. The backend or client initiates a resumable upload.
2. Cloud Storage returns a session URI.
3. The client sends subsequent chunks to the session URI.
4. The session URI acts as a bearer credential for the session's lifetime.

Typically, the backend should initiate the resumable upload and send the session URI to the client. Signing a URL for the initiation request can help when the server and client are geographically distant, but subsequent PUTs use the session URI rather than repeating the initial signed URL.

Session URIs must also be protected like secrets: transmit only over HTTPS, do not log them, and never issue them across tenants. Distinguish session URIs from signed URLs because they have different semantics, lifecycles, and request flows.

## 14. Spring Boot Integration Under the Backend-Authorized Model

### 14.1. Download Flow

~~~mermaid
sequenceDiagram
    participant Browser
    participant API as Spring Boot
    participant DB as Document DB
    participant GCS as Cloud Storage

    Browser->>API: GET /documents/{id}/download-url
    API->>API: Authenticate user
    API->>DB: Find document and tenant
    DB-->>API: bucket/object/generation
    API->>API: Check view permission
    API->>API: Sign URL with download signer
    API-->>Browser: URL + expiresAt
    Browser->>GCS: GET signed URL
    GCS-->>Browser: File bytes
~~~

The backend does not need to read bytes and proxy them to the browser. It grants access only after domain authorization checks. The URL should carry a short expiration and explicit object/generation.

### 14.2. Upload Flow

~~~mermaid
sequenceDiagram
    participant Browser
    participant API as Spring Boot
    participant DB as Document DB
    participant GCS as Cloud Storage

    Browser->>API: POST /documents/upload-url
    API->>API: Authenticate user and quota
    API->>DB: Create PENDING document
    API->>API: Choose object name and signer
    API-->>Browser: PUT signed URL + required headers
    Browser->>GCS: PUT file
    GCS-->>Browser: Upload result
    Browser->>API: POST /documents/{id}/complete
    API->>GCS: Read metadata and checksum
    GCS-->>API: generation, size, contentType
    API->>DB: Mark READY if valid
~~~

If the user abandons the upload, the document remains in `PENDING` state; a cleanup job can handle it according to TTL. Never mark `READY` based solely on a browser callback.

### 14.3. What Should the API Response Return?

It can return:

~~~json
{
  "documentId": "doc-123",
  "method": "PUT",
  "url": "SIGNED_URL",
  "requiredHeaders": {
    "Content-Type": "application/pdf"
  },
  "expiresAt": "2026-11-24T10:30:00Z"
}
~~~

This is an illustrative response. Do not store the URL in the document table as a long-lived attribute. `expiresAt` tells the frontend when to request a new URL; the URL itself remains a secret.

## 15. Testing Signed URLs

### 15.1. Unit Tests

Test the URL-issuing service by mocking the Storage or signer boundary:

- Users without view permission do not receive a URL.
- Tenant A cannot request a URL for Tenant B's document.
- The GET service issues only GET method URLs.
- The PUT service signs only allowed Content-Types.
- Expiration falls within configured limits.
- Object names come from trusted metadata, not arbitrary paths.
- URLs never appear in logs or exception messages.
- New uploads include `ifGenerationMatch=0` when overwrites are disallowed.

There is no need to verify cryptographic signature bytes in unit tests; test options and authorization boundaries.

### 15.2. Integration Tests on a GCP Test Project

1. Create a dedicated signer service account for testing.
2. Grant least-privilege object permissions on the test bucket.
3. Grant Token Creator to the test runtime principal on the signer service account.
4. Enable the IAM Credentials API.
5. Generate a signed GET URL and download the object using an HTTP client without Google credentials.
6. Generate a signed PUT URL, send the exact Content-Type, and verify the object is created.
7. Send the wrong method or wrong Content-Type; confirm the request is rejected.
8. Test an expired URL or an unsigned query parameter.
9. Test a signer missing `storage.objects.get` or a runtime missing `iam.serviceAccounts.signBlob`.
10. Test CORS in a browser test if the frontend calls GCS directly.
11. Verify generation, size, content type, and checksum after upload.
12. Clean up objects and test identities according to procedure.

Do not run destructive tests on production buckets. Never print real URLs in test reports; redact query strings in assertion failures.

### 15.3. Role-Based IAM Checks

| Test principal | Expectation |
| --- | --- |
| Runtime with Token Creator on signer | Can request signatures on behalf of signer |
| Runtime without `iam.serviceAccounts.signBlob` | Cannot generate signatures using that signer |
| Signer with Object Viewer | GET URLs work; PUT URLs are denied |
| Signer with Object Creator | PUT URLs create new objects; cannot overwrite existing objects |
| Signer with Object User | Can read/write/delete objects within role scope |
| Consumer without Google credentials | Can use valid signed URLs |
| Consumer sending wrong method/header | Request is rejected |

## 16. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `IllegalStateException` on `signUrl` | Credential does not implement `ServiceAccountSigner` | Use `ImpersonatedCredentials` or an explicit signer |
| `iam.serviceAccounts.signBlob` denied | Runtime principal lacks Token Creator on signer SA | Check IAM binding on the exact service account |
| `403` when consumer uses URL | Signer lacks object permissions, URL expired, or blocked by policy | Check signer role, expiration, and bucket policy |
| `SignatureDoesNotMatch` | Method/header/query/path differs from signed request | Compare exact method, Content-Type, host, and query params |
| `AccessDenied` on PUT overwrite | Signer lacks permission to delete existing object | Use objectCreator for create-only or a role with create/delete |
| GET URL works with curl but fails in browser | CORS does not allow origin/method/header | Check preflight and bucket CORS configuration |
| URL expires early | Lifetime too long when signing with IAM signBlob under key rotation | Use shorter lifetimes, typically under 12 hours |
| URL stops working after object change | Generation/resource no longer matches or object was deleted | Check generation and object lifecycle |
| URL works after unintended sharing | URL was leaked and has not expired yet | Shorten expiry, address signer/resource exposure, and enforce redaction |
| PUT upload succeeds but document is not READY | Backend has not verified the object or callback did not complete | Run verification/complete step and clean up PENDING records |

### 16.1. Distinguishing URL Creation Errors from URL Usage Errors

- URL creation errors usually involve `ServiceAccountSigner`, `iam.serviceAccounts.signBlob`, disabled APIs, or credential scopes.
- URL usage errors usually involve the signer's object permissions, expiration, method, headers, query parameters, object path, or bucket policy.
- Browser failures can be caused by CORS even when the exact same URL works in `curl`.

Do not grant `roles/storage.admin` to fix signing errors. Identify which principal is missing which permission.

## 17. Comparison with AWS S3 Presigned URLs and Azure SAS

| Aspect | Google Cloud Storage Signed URL | Amazon S3 Presigned URL | Azure Blob SAS |
| --- | --- | --- | --- |
| Signing identity | Typically a service account | AWS IAM principal/credential | Storage account key or user delegation key |
| Signing mechanism | V4 RSA or HMAC depending on credential type | AWS Signature Version 4 | Shared Access Signature |
| Access scope | Signer's IAM permissions | Signer's IAM policy and bucket/object policies | Permissions and resource scope encoded in SAS |
| Lifetime | V4 max 7 days; IAM signBlob subject to key rotation | Depends on signing method and credential/session lifetime | Depends on signed start/expiry and SAS type |
| Request constraints | Method, resource, signed headers/query | Method, resource, signed headers/query | Resource, permissions, protocol, IP/time, and signed fields |
| Java SDK | `Storage.signUrl` | `S3Presigner` | `BlobServiceSasSignatureValues` / user delegation SAS |

All three mechanisms create URLs carrying temporary authority and must be protected like bearer secrets. Differences lie in how signers are identified, permission models, token lifetimes, and canonical signing details. Do not copy IAM roles, expirations, or headers directly from one provider to another without checking semantics.

## 18. Comprehensive Hands-On Exercise

**Context:** The Spring Boot application `document-api` stores multi-tenant documents in bucket `training-documents-dev`. Users with view permission want to download files directly from GCS; users with upload permission want to upload files directly to the bucket.

### Task A — Identity and IAM

1. Create separate runtime and signer service accounts.
2. Enable the IAM Service Account Credentials API.
3. Grant Token Creator to the runtime on the signer service account.
4. Grant Object Viewer to the download signer.
5. Grant Object Creator to the upload signer.
6. Explain why the consumer does not need a Google IAM role.

### Task B — Signed GET

1. Use `ImpersonatedCredentials` as the `ServiceAccountSigner`.
2. Generate a V4 signed URL with a 15-minute expiration.
3. Verify document ownership before signing.
4. Download the file using `curl` without an OAuth token.
5. Generate a URL pinned to a specific generation.

### Task C — Signed PUT

1. Use a backend-generated object name.
2. Sign method PUT and Content-Type `application/pdf`.
3. Use `ifGenerationMatch=0` to prevent overwrites.
4. Upload with `curl` sending the signed header.
5. Call the complete API so the backend verifies metadata/generation/checksum.

### Task D — Security and Testing

- Verify GET fails when the signer lacks objectViewer.
- Verify URL generation fails when the runtime lacks Token Creator.
- Test mismatched method, Content-Type, query parameters, and expired URLs.
- Test CORS in a browser.
- Ensure URLs never appear in logs.
- Verify incomplete uploads are cleaned up.
- Compare signed URLs with S3 presigned URLs and Azure SAS.

**Pass criteria:** Learners distinguish signing principal, signer service account, and URL consumer; grant exact `signBlob` and object permissions; generate V4 GET/PUT URLs in Java; enforce method/header/expiry constraints; and integrate a direct upload/download flow with business verification.

## 19. Key Takeaways

- Signed URLs grant temporary access to anyone holding the URL; treat them like bearer credentials.
- Cloud Storage signed URLs target XML API endpoints and only allow requests matching the signed method, resource, signed headers, query parameters, and expiration.
- The signing principal needs `iam.serviceAccounts.signBlob` on the signer service account; the signer needs object permissions matching GET/PUT/overwrite.
- Use `ImpersonatedCredentials` to sign via the IAM Credentials API without issuing long-lived service account private keys.
- V4 expiration maxes out at 604800 seconds (7 days); when signing via IAM `signBlob`, prefer short lifetimes because service account signing keys rotate.
- Use backend-controlled object names, signed headers, `ifGenerationMatch=0`, and post-upload metadata verification.
- CORS only governs cross-origin browser access; it does not grant permissions or replace signatures.
- Do not log URLs; if per-session control or immediate revocation is required, consider a session-aware proxy or gateway.

### References

- [Signed URLs — Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)
- [V4 signing process with Cloud Storage tools](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers)
- [Create signatures with signBlob](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures)
- [V4 signing process with your own program](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-manually)
- [XML API query parameters and headers](https://docs.cloud.google.com/storage/docs/xml-api/reference-headers)
- [Cloud Storage Java Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [ImpersonatedCredentials Java API](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.ImpersonatedCredentials)
- [Cloud Storage CORS](https://docs.cloud.google.com/storage/docs/cross-origin)

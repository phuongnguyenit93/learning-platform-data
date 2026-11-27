# Permission Scopes, Impersonation, and Tokens in Java Clients

## 1. The Authentication Challenge When Java Calls Google Cloud APIs

A Java or Spring Boot application may run on Cloud Run, GKE, Compute Engine, a developer workstation, or a platform outside Google Cloud. In each environment, the application must prove its identity when calling Google Cloud APIs, while only being allowed to perform the operations it requires.

Three separate questions must be answered:

1. **Who is the application?** This is authentication, typically handled by Application Default Credentials (ADC), a service account, or a workload identity.
2. **What is that identity allowed to do on which resource?** This is authorization, primarily decided by IAM.
3. **For what purpose was the credential or token issued, and how long does it last?** This is where OAuth scopes, access tokens, ID tokens, impersonation, and token lifetimes come into play.

These concepts are related, yet they do not replace one another. Holding a valid access token does not mean the application has permission to read a bucket. Having IAM permissions does not authenticate a request lacking credentials. A broad OAuth scope does not automatically grant extra IAM permissions.

In the **CLOUD_PROVIDERS_GCP** module, learners have seen organizations and projects, IAM, VPC, Cloud Run, GKE, Compute Engine, Storage, and databases. This lesson connects those components to how Java clients discover credentials, use service account identities, borrow identities in a controlled way, and send the right token type to the target API.

## 2. Authentication and Authorization

### 2.1. Authentication: Identifying the Principal

A principal is the identity making the request. In Google Cloud, a principal can be:

- A user's Google Account.
- A service account representing an application or workload.
- A principal from Workload Identity Federation or Workforce Identity Federation.
- A workload identity linked to a service account or granted permissions directly under a supported model.

When a Java client sends a request with credentials, Google Cloud determines the principal from the token. For example, a Cloud Run service may run under the identity **orders-api@PROJECT_ID.iam.gserviceaccount.com**. Requests from the application are then evaluated under that service account identity.

### 2.2. Authorization: IAM Decides Permissions

IAM checks whether the principal holds the required permissions on the resource. Permissions are typically granted via roles:

- **Basic roles:** Owner, Editor, Viewer; very broad in scope and should be avoided in production applications.
- **Predefined roles:** sets of permissions managed by Google by function, such as **roles/storage.objectViewer**.
- **Custom roles:** sets of permissions defined by the organization when predefined roles do not fit requirements.

For example, a service account that only needs to read objects in a bucket can receive **roles/storage.objectViewer** on that bucket. There is no need to grant **roles/storage.admin** at the project level if the application does not manage buckets.

IAM policies can be attached at the organization, folder, project, or resource level. Permissions at parent levels are inherited by child resources. When investigating permissions, check both direct bindings and inherited permissions; a binding at the project level may be broader than the development team intended.

### 2.3. High-Level Model

~~~mermaid
flowchart LR
    A[Java / Spring Boot workload] --> B[ADC or credential source]
    B --> C[Principal and token]
    C --> D[Google Cloud API]
    D --> E{Allowed by IAM and policy?}
    E -- Yes --> F[Perform operation on resource]
    E -- No --> G[401 or 403]
    H[OAuth scope / audience] --> C
~~~

ADC helps the Java client find credentials and obtain a token. The token represents the identity and the appropriate authentication scope. The API additionally validates the scope or audience per the protocol, and then IAM evaluates permissions on the resource.

## 3. IAM Policies and Service Account Permission Scopes

### 3.1. A Service Account Is a Workload Identity

A service account is not a server or a key file. It is a principal representing an application, job, or code-running resource. When a VM, Cloud Run service, or GKE workload uses a service account, requests from the workload authenticate under that identity.

Separate service accounts by workload and responsibility:

| Workload | Example role | Scope to consider |
|---|---|---|
| Object-reading API | **roles/storage.objectViewer** | Target bucket to read |
| Object-writing job | **roles/storage.objectCreator** | Target bucket to write |
| Secret-reading API | **roles/secretmanager.secretAccessor** | Specific secret |
| Service calling internal Cloud Run | **roles/run.invoker** | Target Cloud Run service |
| Resource-inventory metadata job | Appropriate Cloud Asset API reader role | Project or folder to inventory |
| Deployment pipeline | Deployment roles by service and target | Assigned project/environment |

The role names in this table are examples. Check the current catalog of roles and permissions for each service before granting access. A workload often needs several narrow roles on distinct resources rather than one broad project-level role.

### 3.2. Attaching a Service Account to a Resource: actAs

A user or service account creating a VM, Cloud Run service, or executable resource needs permission to attach a service account to that resource. The key permission is **iam.serviceAccounts.actAs**. The role commonly used to grant this permission is **Service Account User**:

**roles/iam.serviceAccountUser**

This role allows a principal to attach a service account to a resource. It does not by itself allow the principal to mint short-lived access tokens to impersonate the service account via the IAM Credentials API.

Example: an engineer deploys a Cloud Run service and selects **orders-runtime@PROJECT_ID.iam.gserviceaccount.com**. The engineer needs permission to create/update the Cloud Run service and `actAs` permission on that service account. When the service runs, the application uses the `orders-runtime` identity; the engineer does not automatically inherit all permissions of the runtime service account.

### 3.3. Issuing Short-Lived Credentials: Service Account Token Creator

**Service Account Token Creator**:

**roles/iam.serviceAccountTokenCreator**

This role allows a principal to mint short-lived credentials for a service account, including:

- OAuth 2.0 access tokens.
- OpenID Connect (OIDC) ID tokens.
- Blob and JWT signatures through the corresponding signing permissions.
- Delegation between service accounts in an impersonation chain.

Key permissions:

| Permission | Effect |
|---|---|
| **iam.serviceAccounts.getAccessToken** | Generates an OAuth access token for the service account |
| **iam.serviceAccounts.getOpenIdToken** | Generates an OIDC ID token |
| **iam.serviceAccounts.signBlob** | Signs binary data, usable in signed URL flows |
| **iam.serviceAccounts.signJwt** | Signs a JWT |
| **iam.serviceAccounts.implicitDelegation** | Supports delegation chains |

This is a sensitive permission. The principal can mint tokens bearing the target service account's identity and exercise whatever permissions that service account holds. Grant this role directly on the target service account; avoid granting it at the project or folder level when only one account needs impersonation.

If only OIDC ID token generation is needed, consider the narrower role:

**roles/iam.serviceAccountOpenIdTokenCreator**

This role provides only the permission to create ID tokens. Do not grant the broader Service Account Token Creator role if the workload only needs that capability.

### 3.4. Workload Identity User for GKE

With GKE Workload Identity Federation, a Kubernetes service account can be linked to a Google service account so the workload receives the appropriate identity. The role commonly granted on the target service account is:

**roles/iam.workloadIdentityUser**

This role lets the GKE workload identity impersonate the service account within the configured scope. This model is specifically for GKE workloads; do not confuse it with **roles/iam.serviceAccountUser** for attaching a service account to a resource, or **roles/iam.serviceAccountTokenCreator** used in other impersonation flows.

### 3.5. Comparing Commonly Confused Roles

| Role | When to use | Does NOT mean |
|---|---|---|
| **roles/iam.serviceAccountUser** | Attaching a service account to a VM, Cloud Run, or supported resource | Permission to mint access tokens for impersonation |
| **roles/iam.serviceAccountTokenCreator** | Creating access tokens, ID tokens, or signing JWTs/blobs for a service account | Permission to read all resources owned by the service account |
| **roles/iam.serviceAccountOpenIdTokenCreator** | Only needing to generate OIDC ID tokens | Permission to mint access tokens or sign blobs |
| **roles/iam.workloadIdentityUser** | Linking a GKE workload identity to a service account | A role to access buckets, secrets, or databases |

These roles govern how a principal uses a service account's identity. Permissions to access business resources must still be granted to the target service account itself.

## 4. OAuth Scopes and IAM Permissions

### 4.1. Two Separate Control Layers

An OAuth scope defines the boundaries an access token is permitted to request when calling an API. An IAM role contains permissions to perform actions on resources. A request usually must satisfy both the API's scope requirements and IAM permissions.

Example:

- A token carries the scope **https://www.googleapis.com/auth/cloud-platform**.
- The service account only holds **roles/storage.objectViewer** on the `reports` bucket.
- The application can read objects within what IAM allows; a broad scope does not turn the service account into a Storage Admin.

A narrow scope can restrict how a token is used, but it does not replace least privilege in IAM. Conversely, granting an IAM role does not make a token lacking the required scope valid.

### 4.2. Common Scopes

| Scope | Purpose |
|---|---|
| **https://www.googleapis.com/auth/cloud-platform** | General scope for Google Cloud APIs |
| **https://www.googleapis.com/auth/devstorage.read_only** | Read-only access scope for Cloud Storage |
| **https://www.googleapis.com/auth/devstorage.read_write** | Read/write access scope for Cloud Storage |
| **https://www.googleapis.com/auth/iam** | Calling supported IAM functions, such as impersonation flows |
| **https://www.googleapis.com/auth/userinfo.email** | Accessing user email information in supported flows |

The specific API method determines which scopes are accepted. Check the API reference when selecting scopes; do not copy scopes blindly from one API to another.

### 4.3. Access Scopes on Compute Engine

A Compute Engine VM has access scopes associated with its service account. This acts as an additional restriction on tokens issued via the metadata server. In practice, the standard pattern is to set the `cloud-platform` scope on the VM and enforce fine-grained access using narrow IAM roles.

If a VM only has the Cloud Storage read-only scope, even if the service account has an IAM role to write objects, tokens can still be blocked by the access scope. If a VM has the `cloud-platform` scope, that does not grant extra IAM permissions; the service account can still perform only what IAM permits.

Do not confuse VM access scopes with IAM roles. When troubleshooting 403 errors on Compute Engine, check both the IAM policy and the VM's access scopes. Cloud Run and other environments have their own credential models and do not directly mirror VM access scope settings.

## 5. Application Default Credentials in Java

### 5.1. ADC Keeps Code Unchanged Across Environments

Application Default Credentials (ADC) is the mechanism Google Auth Library uses to automatically locate credentials suited to the runtime environment. Cloud Client Libraries for Java can use ADC without requiring the app to read keys or call token endpoints directly.

In production on Google Cloud, prefer attaching a **user-managed service account** to the compute resource:

- Cloud Run services or jobs use the service account configured on the revision/job.
- Compute Engine VMs use the service account attached to the instance.
- GKE workloads use Workload Identity Federation for GKE.
- Workloads outside Google Cloud use Workload Identity Federation with an external identity provider.

Do not rely on overly broad default service accounts. Create dedicated service accounts and assign least-privilege roles per workload.

### 5.2. ADC Credential Discovery Order

Google Auth Library for Java searches for credentials across these main sources:

1. The file pointed to by the **GOOGLE_APPLICATION_CREDENTIALS** environment variable.
2. The local ADC file created by **gcloud auth application-default login**.
3. Google Cloud environment credentials via the metadata server or corresponding built-in credential source.

The file in `GOOGLE_APPLICATION_CREDENTIALS` can be a service account key, an external account configuration for Workload Identity Federation, or Workforce Identity Federation. If the environment variable points to an old file, the app may use different credentials from the service account attached to Cloud Run/VM. When debugging, check the actual ADC source first.

Command to create local user ADC:

~~~bash
gcloud auth application-default login
~~~

**gcloud auth login** and **gcloud auth application-default login** manage two separate credential configurations. Logging in to the `gcloud` CLI does not automatically mean the Java client uses those credentials.

### 5.3. Example: Java Client Using ADC

Cloud Client Libraries for Java typically use ADC automatically:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class StorageAccess {
    public Storage createClient() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

The same code can run locally with the developer's ADC, on Cloud Run with the revision's service account, or on GKE with Workload Identity Federation. What changes is the credential source and the principal's IAM policy—not the Storage calling code.

### 5.4. Using ADC in Spring Boot

Spring Boot should initialize clients in the configuration layer and inject them into services. Avoid creating clients or calling the metadata server on every request.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GoogleCloudClientConfig {

    @Bean
    Storage storageClient() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Business services receive the client via constructor injection:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class ReportStorageService {

    private final Storage storage;

    public ReportStorageService(Storage storage) {
        this.storage = storage;
    }

    public Blob findReport(String bucket, String objectName) {
        return storage.get(bucket, objectName);
    }
}
~~~

Do not pass an access token string into a business service constructor. Inject the client or a refresh-capable `Credentials` object. The client library handles attaching credentials to requests and refreshing tokens as needed.

## 6. Service Account Impersonation

### 6.1. What Is Impersonation?

Service account impersonation allows an authenticated principal to ask Google Cloud to issue short-lived credentials for another service account. The initial principal is the **source principal**; the service account whose identity is borrowed is the **target service account**.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Source as Source credential
    participant IAM as IAM Credentials API
    participant Target as Target service account
    participant API as Google Cloud API
    App->>Source: Obtain initial credentials via ADC
    App->>IAM: generateAccessToken(target, scopes, lifetime)
    IAM->>IAM: Check Token Creator and delegation
    IAM-->>App: Short-lived access token of target
    App->>API: Send request with token
    API->>Target: Identify token principal
    API->>API: Check IAM on resource
    API-->>App: Result
~~~

The source principal does not need direct permissions on business resources if it is only authorized to impersonate the target service account. The target service account must hold the necessary IAM roles on the resources the application accesses.

Impersonation is useful when:

- Developers need to test an application with production-like permissions.
- A pipeline needs to use a dedicated deployment identity.
- A workload needs to access resources as another service account across a security boundary.
- An organization wants to grant temporary access without issuing service account keys.

Impersonation creates short-lived credentials and does not require downloading the target's private key locally.

### 6.2. Prerequisites for Impersonation

Before using `ImpersonatedCredentials` in Java:

1. Enable the **Service Account Credentials API** (`iamcredentials.googleapis.com`) in the source project performing the impersonation request.
2. Grant **roles/iam.serviceAccountTokenCreator** to the source principal on the target service account.
3. Grant business IAM roles to the target service account on the target resources.
4. Choose appropriate OAuth scopes for the generated token.
5. Set a short lifetime suited to the task duration.

The Token Creator role should be bound directly on the target service account when impersonating a single account. Avoid granting it at the project or folder level unnecessarily.

### 6.3. Java Example with ImpersonatedCredentials

The example below lets the current ADC credentials impersonate a read-only Cloud Storage service account. Source credentials need Token Creator on the target service account; the target service account needs **roles/storage.objectViewer** on the target bucket.

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

import java.io.IOException;
import java.util.Arrays;

public class ImpersonatedStorageClient {

    public Storage createClient() throws IOException {
        GoogleCredentials sourceCredentials =
            GoogleCredentials.getApplicationDefault()
                .createScoped(
                    Arrays.asList("https://www.googleapis.com/auth/iam")
                );

        ImpersonatedCredentials targetCredentials =
            ImpersonatedCredentials.newBuilder()
                .setSourceCredentials(sourceCredentials)
                .setTargetPrincipal(
                    "report-reader@PROJECT_ID.iam.gserviceaccount.com"
                )
                .setScopes(
                    Arrays.asList(
                        "https://www.googleapis.com/auth/devstorage.read_only"
                    )
                )
                .setLifetime(1800)
                .build();

        return StorageOptions.newBuilder()
            .setProjectId("PROJECT_ID")
            .setCredentials(targetCredentials)
            .build()
            .getService();
    }
}
~~~

In this example:

- `sourceCredentials` is the initial identity supplied by ADC.
- The `iam` scope enables the source credential to perform the IAM Credentials API call flow as configured.
- `targetPrincipal` is the service account to impersonate.
- The `devstorage.read_only` scope restricts the OAuth purpose of the token to read-only Storage access.
- `setLifetime(1800)` requests a token lifetime of 1,800 seconds (30 minutes).

This code illustrates a Storage reader client. Replace the project, email, and scopes to match your actual system. Do not reuse this scope list for a different API without checking its method documentation.

### 6.4. Impersonation in Local Development

Developers can create local ADC so client libraries impersonate a service account automatically:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=report-reader@PROJECT_ID.iam.gserviceaccount.com
~~~

The Java client then simply calls:

~~~java
GoogleCredentials credentials =
    GoogleCredentials.getApplicationDefault();
~~~

This helps validate the target service account's permissions without downloading JSON keys. The developer needs Token Creator on the target service account, and the target service account needs the required business roles.

### 6.5. Delegation Chains

Some organizations require an identity chain A → B → C → target instead of direct impersonation from the source principal. Google Auth Library for Java supports a delegate list via `setDelegates`.

Each link in the chain must grant Token Creator to the preceding principal on the next service account. For example, source has Token Creator on B, B has Token Creator on C, and C has Token Creator on target. Long chains increase auditing and debugging complexity; use them only when a genuine administrative boundary demands it.

Do not configure self-impersonation where a service account mints new tokens for itself from a short-lived token. Google Cloud blocks certain self-impersonation patterns because they can create an infinite credential-refresh loop if a token is stolen.

## 7. Access Tokens, ID Tokens, and Signed Tokens

Not every token works for the same type of endpoint.

### 7.1. OAuth 2.0 Access Token

An access token is a bearer credential normally used to call Google Cloud APIs. Clients send it in the header:

~~~http
Authorization: Bearer ACCESS_TOKEN
~~~

The token represents the principal and carries requested scopes. The API further checks the principal's IAM permissions on the resource. Never place access tokens in query strings, as URLs are easily recorded in logs, proxies, or browser histories.

### 7.2. OIDC ID Token

An ID token is a Google-signed JWT containing identity claims and an `aud` (audience) claim. It is used to authenticate to a specific service or application, such as:

- Calling a Cloud Run service that requires authentication.
- Calling Cloud Run functions.
- Calling an application protected by Identity-Aware Proxy (IAP).
- Calling API Gateway or Cloud Endpoints in supported setups.

`aud` must match the audience expected by the target service. For Cloud Run, this is typically the service URL; for IAP, the audience may be the OAuth client ID per IAP configuration.

To invoke a private Cloud Run service, the service account represented in the ID token must also hold **roles/run.invoker** on the target Cloud Run service. A valid token proves identity only; IAM decides whether that identity may invoke the service.

If the application runs on Cloud Run, Compute Engine, or GKE with an attached/linked service account, the metadata server can supply ID tokens for the workload. When using its own workload identity, the app does not need Token Creator on its own service account; the service account still needs Invoker on the target service. If impersonating another service account to mint an ID token, grant the ID token creation role on the target service account to the source principal.

### 7.3. Signed JWTs and Signed Blobs

The IAM Credentials API can sign JWTs or binary payloads using Google-managed private keys. Private keys are never downloaded to the application. These flows suit protocols or features needing signatures, such as signed URLs or certain federated auth flows.

Do not use a signed JWT in place of a normal access token if an API expects an OAuth access token. Choose credentials according to the endpoint's authentication contract.

### 7.4. Downscoped Access Tokens

Credential Access Boundary (CAB) allows generating a downscoped token from a broader source credential, restricting access to a specific set of resources and permissions. A typical use case is a token broker issuing tokens to read objects in a specific bucket or prefix for another workload.

Downscoping is especially useful when an intermediary service must grant temporary access to a consumer. The consumer receives only a narrowly scoped token instead of the broad source credential. Verify Credential Access Boundary support limits for target services; do not assume CAB applies to every Google Cloud API.

## 8. Token Lifetime, Refresh, and Lifecycle Management

### 8.1. Token Lifetime

Access tokens minted via service account impersonation have a default maximum lifetime of **1 hour (3,600 seconds)**. Organizations can allow up to **12 hours (43,200 seconds)** for designated service accounts under the Organization Policy constraint:

**constraints/iam.allowServiceAccountCredentialLifetimeExtension**

Increase lifetimes only when a concrete operational requirement exists. Longer-lived tokens widen the window during which an exposed token could be abused. Normally, choose short task-appropriate lifetimes such as 15–60 minutes and let the client library refresh as needed.

ID tokens minted via the IAM Credentials API are short-lived; `generateIdToken` documentation specifies validity of 1 hour. For the metadata server or other workload identities, rely on the credential provider and the environment's documentation.

### 8.2. Token Refresh in Java Clients

Do not fetch an access token once at application startup and keep that raw string for the lifetime of the process. Tokens expire; once expired, subsequent requests will fail with `401 UNAUTHENTICATED`.

Retain the `GoogleCredentials`, `ImpersonatedCredentials`, or `IdTokenCredentials` object and pass it to the client library or HTTP credentials adapter. Google Auth Library manages token state and refreshes according to the credential type when requests are sent.

For an explicitly loaded credential, `refreshIfExpired()` can be called before reading a token. However, Cloud Client Libraries normally invoke the credential refresh mechanism automatically when needed; the application does not need to write per-request refresh loops.

If you construct `GoogleCredentials` from a static `AccessToken`, that credential lacks refresh information to request a new token. When refresh is required, supply a refresh-capable credential provider or fall back to ADC/impersonation sources.

### 8.3. Protecting Tokens

- Never log access tokens, ID tokens, refresh tokens, or `Authorization` headers.
- Never write tokens into databases, source code, Docker images, build artifacts, or URLs.
- Never transmit tokens over unencrypted channels.
- Never share tokens across distinct users or workloads.
- Never cache tokens beyond their expiry.
- Avoid calling `toString()` on credentials for production debugging; some implementations may include raw token material in request metadata.
- If a credential leaks, identify affected principals and resources, revoke impersonation permissions if needed, rotate the credential source, and monitor audit logs.

Short-lived tokens reduce long-term exposure risk, but do not replace protecting source credentials and enforcing least-privilege IAM.

## 9. Java Example: Calling Cloud Run with an ID Token

Suppose a Spring Boot service needs to call an internal Cloud Run service with authentication enabled. The app uses the workload's attached service account or an impersonated service account authorized to invoke the target service.

Example using `IdTokenCredentials` and `HttpCredentialsAdapter`:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import com.google.auth.http.HttpCredentialsAdapter;
import com.google.api.client.http.GenericUrl;
import com.google.api.client.http.HttpRequest;
import com.google.api.client.http.HttpRequestFactory;
import com.google.api.client.http.HttpResponse;
import com.google.api.client.http.javanet.NetHttpTransport;

public class InternalCloudRunClient {

    public String call(String serviceUrl) throws Exception {
        GoogleCredentials credentials =
            GoogleCredentials.getApplicationDefault();

        if (!(credentials instanceof IdTokenProvider)) {
            throw new IllegalStateException(
                "Credential provider does not support ID tokens"
            );
        }

        IdTokenCredentials idTokenCredentials =
            IdTokenCredentials.newBuilder()
                .setIdTokenProvider((IdTokenProvider) credentials)
                .setTargetAudience(serviceUrl)
                .build();

        HttpRequestFactory requestFactory =
            new NetHttpTransport().createRequestFactory(
                new HttpCredentialsAdapter(idTokenCredentials)
            );

        HttpRequest request =
            requestFactory.buildGetRequest(new GenericUrl(serviceUrl));

        try (HttpResponse response = request.execute()) {
            return response.parseAsString();
        }
    }
}
~~~

`HttpCredentialsAdapter` attaches credentials to the request. `IdTokenCredentials` fetches an ID token matching the audience; the client never manually concatenates bearer token strings. In production, use a managed HTTP transport/client and configure timeouts, connection pooling, and retries according to service requirements.

The service account represented in the ID token needs **roles/run.invoker** on the target Cloud Run service. If the token is generated via impersonation, the source principal also needs permission to mint ID tokens for the target service account. If only minting ID tokens, **roles/iam.serviceAccountOpenIdTokenCreator** is the narrower choice when sufficient for the flow.

## 10. Spring Boot: Environment-Based Credential Configuration

An application should separate credential creation from business logic. You can configure a `Credentials` bean or create client beans directly. With Cloud Client Libraries, the simplest approach is letting ADC select the credential source automatically.

If impersonation is required, construct `ImpersonatedCredentials` in a `@Configuration` class and inject the configured client into services. Load the target service account email from environment configuration; never hardcode credentials or tokens.

Example Storage bean using ADC:

~~~java
@Configuration
public class GcpStorageConfiguration {

    @Bean
    public Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Example Storage bean using impersonation:

~~~java
@Configuration
public class GcpImpersonationConfiguration {

    @Bean
    public Storage storage(
        @Value("${gcp.auth.target-service-account}") String targetServiceAccount
    ) throws IOException {

        GoogleCredentials source =
            GoogleCredentials.getApplicationDefault()
                .createScoped(
                    Collections.singletonList(
                        "https://www.googleapis.com/auth/iam"
                    )
                );

        ImpersonatedCredentials target =
            ImpersonatedCredentials.newBuilder()
                .setSourceCredentials(source)
                .setTargetPrincipal(targetServiceAccount)
                .setScopes(
                    Collections.singletonList(
                        "https://www.googleapis.com/auth/devstorage.read_only"
                    )
                )
                .setLifetime(1800)
                .build();

        return StorageOptions.newBuilder()
            .setCredentials(target)
            .build()
            .getService();
    }
}
~~~

This example requires the corresponding imports such as `GoogleCredentials`, `ImpersonatedCredentials`, `Storage`, `StorageOptions`, `Value`, `Bean`, `Configuration`, `Collections`, and `java.io.IOException`. The target service account setting should be supplied via environment-specific configuration or appropriate config/secret management. While a service account email is not a secret, choosing the target is a privilege decision requiring review.

Do not instantiate clients inside each business method. Reusing clients across the application lifecycle leverages connection pooling and credential refreshing. If the application accesses multiple target service accounts with distinct permissions, create separate client beans per role rather than mutating shared credentials across requests.

## 11. Practical Scenario: Spring Boot on Cloud Run Reading Storage and Calling an Internal Service

An `invoice-api` application running on Cloud Run needs to:

- Read PDF files from the `invoice-private` bucket.
- Call `pdf-renderer`, a private Cloud Run service.
- Log processing metadata and return results to callers.

### Identity Design

Create a dedicated runtime service account:

**invoice-api-runtime@PROJECT_ID.iam.gserviceaccount.com**

Grant permissions:

| Resource | Role | Reason |
|---|---|---|
| Bucket `invoice-private` | **roles/storage.objectViewer** | Read PDF files |
| Cloud Run service `pdf-renderer` | **roles/run.invoker** | Invoke internal service |

Attach this service account to the Cloud Run revision of `invoice-api`. The Java client uses ADC to obtain credentials from the environment. No service account JSON key needs to be placed inside the container.

### Call Flow

1. Cloud Run starts the revision with the `invoice-api-runtime` service account.
2. The Java Storage client uses ADC to obtain credentials and read objects from the bucket.
3. When calling `pdf-renderer`, the app fetches an ID token with audience set to the `pdf-renderer` service URL.
4. `pdf-renderer` validates the ID token and checks `roles/run.invoker` for `invoice-api-runtime`.
5. The app logs request ID, service name, and processing status; it does not log tokens or sensitive payloads.

### Local Development

Developers can use personal ADC if granted direct access to test resources. To verify the exact permissions of the runtime service account, developers can impersonate `invoice-api-runtime` using local ADC. In that case:

- The developer needs Token Creator on the target service account.
- The runtime service account needs the corresponding Storage Viewer and Cloud Run Invoker roles.
- Java code continues using `GoogleCredentials.getApplicationDefault()`.

Keep test projects or buckets separate from production so developers do not need access to real data. Using impersonation verifies runtime identity permissions without copying private keys.

## 12. Common Errors and Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| 401 UNAUTHENTICATED | Missing token, expired token, wrong credential source, or token rejected by API | Check ADC source, refresh flow, system clock, and token type |
| 403 PERMISSION_DENIED | Principal authenticated, but lacks IAM permissions | Identify actual principal, check resource IAM policy and inherited roles |
| 403 despite having IAM role | Mismatched OAuth scope or Compute Engine access scope | Check required scopes and VM access scopes |
| `iam.serviceAccounts.getAccessToken` denied | Source principal lacks Token Creator on target, or IAM Credentials API disabled | Check role on the exact target and API enablement in source project |
| Cannot attach service account | Missing `iam.serviceAccounts.actAs` | Check `roles/iam.serviceAccountUser` on the service account |
| Calling Cloud Run returns 401/403 | Used access token instead of ID token, wrong audience, or missing Invoker | Use an ID token with exact audience and check `roles/run.invoker` |
| GKE workload does not get expected identity | Workload Identity Federation for GKE or KSA/GSA binding misconfigured | Check KSA, provider, `roles/iam.workloadIdentityUser` binding, and metadata server |
| Java works locally but fails on Cloud Run | Local ADC differs from runtime service account | Verify service account attached to revision and resource IAM roles |
| First request works, later requests fail | App holds a static expired token string | Use a refresh-capable credential object instead of caching a token string |
| Impersonation works but target API rejects | Target service account lacks business roles or token scope is wrong | Check target IAM roles and token scopes |

Do not infer the principal solely from the application name. In environments with multiple service accounts, verify the actual identity using credential configuration, workload metadata, or audit logs.

## 13. Auditing and Governing Impersonation

Impersonation changes which principal is used to access resources. Organizations must therefore track both identities: which source principals are permitted to impersonate and which target service accounts are being used.

Recommended controls:

- Grant Token Creator directly on the target service account; avoid overly broad grants.
- Periodically review principals permitted to impersonate sensitive service accounts.
- Restrict who can modify IAM policies on service accounts.
- Monitor audit logs related to the IAM Credentials API and resource operations.
- Document justification, owner, and expiration for exceptional impersonation grants.
- Use separate service accounts per workload or environment.
- Revoke impersonation permissions when no longer needed.
- Audit service account keys and remove unnecessary keys.

A service account defines a workload's security boundary. Anyone able to modify a service account's IAM policy or impersonate that service account can directly affect the resources the workload accesses.

## 14. Production Readiness Checklist for Java Clients

### Identity and ADC

- [ ] Application uses ADC or a credential provider suited to the environment.
- [ ] Cloud Run/Compute Engine attaches a user-managed service account with least privilege.
- [ ] GKE workloads use Workload Identity Federation for GKE.
- [ ] Workloads outside Google Cloud prefer Workload Identity Federation over JSON keys.
- [ ] No stale key file in `GOOGLE_APPLICATION_CREDENTIALS` shadows the intended runtime identity.

### IAM and Scopes

- [ ] IAM roles are granted at the narrowest possible resource scope.
- [ ] `actAs`, Token Creator, and Workload Identity User are properly distinguished.
- [ ] OAuth scopes are selected per API method.
- [ ] The `cloud-platform` scope is not mistaken for Owner or Editor permissions.
- [ ] On Compute Engine, access scopes are verified alongside IAM policies.

### Impersonation and Tokens

- [ ] Source principals can impersonate only the target service accounts they require.
- [ ] IAM Credentials API is enabled in the source project.
- [ ] Target service account holds the business roles on target resources.
- [ ] Access tokens and ID tokens are each used for their intended purpose.
- [ ] ID tokens carry the exact audience and the principal holds Invoker when calling Cloud Run.
- [ ] Token lifetimes are short and appropriate for the task.
- [ ] Java clients retain refresh-capable credential objects.
- [ ] Tokens are never logged, persisted, or passed in URLs.
- [ ] Self-impersonation and delegation chains are avoided unless explicitly required.

### Spring and Operations

- [ ] Credentials/clients are configured and injected via Spring beans.
- [ ] Clients are reused rather than created per request.
- [ ] Local, staging, and production use distinct identities and resource scopes.
- [ ] Audit logs and periodic IAM review processes are maintained.
- [ ] Runbooks exist for 401, 403, scope mismatches, and token expiry.

## 15. Self-Check Questions

1. How do authentication and authorization differ when Java calls Cloud Storage?
2. Why does the `cloud-platform` OAuth scope not grant a service account `roles/storage.admin` permissions?
3. How does `roles/iam.serviceAccountUser` differ from `roles/iam.serviceAccountTokenCreator` in permissions and purpose?
4. When one Cloud Run service calls another private Cloud Run service, why is an ID token usually required instead of an access token?
5. In `ImpersonatedCredentials`, what do the source principal and target service account represent?
6. Why does the target service account still need IAM roles on target resources even when the source holds Token Creator?
7. When should you use `roles/iam.serviceAccountOpenIdTokenCreator` instead of Token Creator?
8. Why should you not store a `String` access token in a singleton Spring bean for the entire application lifecycle?
9. If Java runs on a VM, why must both IAM roles and access scopes be checked?
10. Which risks does Workload Identity Federation reduce compared to service account JSON keys?

## References

- [Authentication for Google Cloud APIs and services](https://docs.cloud.google.com/docs/authentication)
- [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Authenticate your requests with Java](https://docs.cloud.google.com/java/docs/authentication)
- [Get started with Google Auth Library for Java](https://docs.cloud.google.com/java/getting-started/getting-started-with-google-auth-library)
- [Roles for service account authentication](https://docs.cloud.google.com/iam/docs/service-account-permissions)
- [Use service account impersonation](https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation)
- [Service account impersonation](https://docs.cloud.google.com/iam/docs/service-account-impersonation)
- [Create short-lived credentials for a service account](https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct)
- [Restrict service account usage and token lifetime](https://docs.cloud.google.com/organization-policy/restrict-service-accounts)
- [Get an ID token](https://docs.cloud.google.com/docs/authentication/get-id-token)
- [IdTokenCredentials Java reference](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.IdTokenCredentials)
- [ImpersonatedCredentials Java reference](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.ImpersonatedCredentials)
- [Credential Access Boundary and downscoped tokens](https://docs.cloud.google.com/iam/docs/downscoping-short-lived-credentials)
- [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)

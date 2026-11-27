# Managed Identity, SAS, and Azure Storage Access Permissions in Spring Boot

## 1. Problem Statement and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we integrate Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud ecosystems. This lesson belongs to the **Azure Storage** chapter and addresses three questions that always arise when connecting an application to Blob Storage, Queue Storage, or Azure Files:

1. **Who is the application?** How does Azure authenticate identity when code runs on a developer's machine, on Azure App Service, or inside a container?
2. **What is that identity allowed to do?** Where are permissions granted to read, write, or delete blobs; send/receive queue messages; or access a file share?
3. **How do we grant temporary access to a browser or another service?** When should a **Shared Access Signature (SAS)** be used, and how do we restrict its scope, lifetime, and actions?

Running example: a Spring Boot API accepts PDF resumes, stores them in a private `documents` container, and sends a processing job via Azure Queue Storage; signed-in users can download documents they own. The API runs in Azure using a **managed identity**. A browser only receives a **read-only SAS URL for a single blob** if the backend has verified authorization.

Learning objectives:

- Distinguish **authentication** (verifying identity), **authorization** (granting access rights), and **network access** (network path).
- Choose between **system-assigned** and **user-assigned managed identity** and understand token acquisition principles.
- Grant least-privilege **data-plane** permissions for Blob and Queue, and understand the boundaries of Azure Files SMB/NFS/REST.
- Distinguish **user delegation SAS**, **service SAS**, and **account SAS**, and understand the risks of exposed account keys and SAS tokens.
- Configure Spring Cloud Azure/Azure SDK per environment, generate short-lived SAS tokens, diagnose 401/403 errors, and design tests.

## 2. Three Layers of Access Control: Identity, Permissions, and Network

A successful request generally must satisfy all three simultaneously:

~~~mermaid
flowchart LR
    A[Spring Boot / Client] --> I{Authentication}
    I -->|Microsoft Entra token / SAS / key| R{Authorization}
    R -->|RBAC or SAS signature and scope| N{Network}
    N -->|Firewall / endpoint / DNS / TLS| S[(Azure Storage)]
    I -->|Invalid| E1[Denied]
    R -->|Invalid| E2[Denied]
    N -->|Invalid| E3[Unreachable or blocked]
~~~

The three layers have distinct responsibilities:

| Layer | Core Question | Examples |
|---|---|---|
| Authentication | Who is calling? Or what access credential does the request carry? | Microsoft Entra ID token of a managed identity; SAS token; account key |
| Authorization | Which actions can the principal/token perform on which resource? | `Storage Blob Data Reader` on container `documents`; SAS with only `r` permission on one blob |
| Network | Can the request reach the endpoint? | Storage firewall, private endpoint, NSG, DNS, HTTPS |

**Do not confuse management plane with data plane.** An account with `Contributor` on Azure Resource Manager can manage Azure resources but cannot necessarily read Blob/Queue data using a Microsoft Entra token. Conversely, an identity with `Storage Blob Data Reader` can read granted blobs but does not automatically have permission to create a storage account. Certain management-plane permissions, especially the permission to **list account keys**, indirectly enable data access via Shared Key; therefore both planes must be controlled.

**A SAS is a bearer credential:** anyone holding a valid SAS URL can use it within the scope it grants, unless blocked by other conditions (such as network rules, expiration, or restricted IP/protocol). A SAS **does not automatically verify** who the end user logged into your application is.

## 3. What Is a Managed Identity?

A **managed identity** is an application identity managed by Azure in Microsoft Entra ID. The resource running your application can request an **access token** to call Azure Storage without storing client secrets or passwords in code. The SDK uses that token to call OAuth-enabled Azure Storage endpoints.

### 3.1. System-Assigned vs. User-Assigned

| Criterion | System-assigned managed identity | User-assigned managed identity |
|---|---|---|
| Lifecycle | Tied to a single Azure resource; deleted when that resource is deleted | Standalone Azure resource with its own lifecycle |
| Reusability | Typically bound to that specific resource | Can be assigned to multiple supported resources |
| Client configuration | Runtime usually discovers the resource-bound identity automatically | May require **client ID** (or another SDK-supported identifier) to select the right identity |
| Permissions | Assign RBAC to the resource's principal | Assign RBAC to the user-assigned identity's principal |
| When appropriate | A standalone application whose identity lifecycle matches the app | Multiple deployments sharing an identity or preserving identity across infrastructure changes |

Creating a managed identity **is not enough to read/write Blobs**: you still must assign the appropriate **data-plane** role on the storage account or container. Conversely, assigning a role to an identity **does not make the app use that identity** if credential selection is misconfigured.

### 3.2. Access Token Flow

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot
    participant SDK as Azure Identity SDK
    participant MI as Managed identity endpoint
    participant ST as Azure Blob Storage
    APP->>SDK: Request token for Azure Storage
    SDK->>MI: Fetch token for assigned managed identity
    MI-->>SDK: Time-limited access token
    SDK-->>APP: Credential manages token/refresh
    APP->>ST: Call API with Bearer token
    ST->>ST: Validate token and data-plane permissions
    ST-->>APP: Data or 401/403 error
~~~

Tokens have finite lifetimes; the Azure Identity SDK handles token acquisition and refresh. Never persist long-lived access tokens to a database, log tokens, or hardcode a token as an application config variable.

### 3.3. Local, CI/CD, and Production

- **Local:** developers can sign in with `az login` or a compatible IDE so the SDK obtains a token; assign permissions to the **developer identity** or use test resources.
- **Azure production:** prefer managed identity; grant RBAC to the **principal of the running identity**. For user-assigned identities, ensure the app selects the right client ID.
- **CI/CD:** when interacting with Azure, prefer workload identity federation/OIDC or identities without long-lived secrets; separate resource deployment permissions from application data-access permissions.

`DefaultAzureCredential` is convenient because it probes supported identity sources, but that flexibility requires discipline: local runs may use a developer identity while Azure production uses a managed identity with completely different permissions. When diagnosing issues, identify the **actual effective principal** instead of just saying "managed identity is enabled".

## 4. Azure RBAC for Blob, Queue, and Azure Files

### 4.1. Distinguishing Scope and Operations

A role assignment generally consists of **principal + role + scope**:

~~~text
Principal: Managed identity of document-api
Role:      Storage Blob Data Contributor
Scope:     Storage account / container documents

Principal: Managed identity of document-worker
Role:      Storage Queue Data Message Processor
Scope:     Queue document-jobs (when scope is supported)
~~~

Choose the smallest scope that satisfies requirements. Do not grant permissions at the subscription level simply for convenience; an app reading one container should be scoped to that container when the RBAC/operation model allows.

| Use Case | Role or Permission Layer to Consider | Notes |
|---|---|---|
| Read/list/download blobs | **Storage Blob Data Reader** | Grants data read access at the assigned scope; app must still enforce end-user authorization |
| Upload, modify, delete blobs | **Storage Blob Data Contributor** | Broader than Reader; assign only to services that genuinely write |
| Send Queue messages | **Storage Queue Data Message Sender** | Fits producers that only enqueue |
| Receive/process/delete Queue messages | **Storage Queue Data Message Processor** | Fits job-processing workers |
| Manage multiple Queue data operations | **Storage Queue Data Contributor** | Evaluate instead of combining producer and worker under one principal |
| Generate user delegation key for Blob | **Storage Blob Delegator** or role with matching action | Key generation permission has its own scope, see section 6 |
| Azure Files via SMB | **Storage File Data SMB Share ...** roles plus filesystem/ACL permissions as applicable | Must determine SMB auth method and share/file permission levels |
| Azure Files via REST | REST/OAuth credentials and roles supported for the API/features in use | Do not infer REST permissions from SMB roles |
| Azure Files via NFS | Check NFS security model, networking, and POSIX permissions | Do not equate with Blob's Entra OAuth |

Role names can vary across features and environments; before deploying, check the current Azure Storage built-in roles and actual action permissions. Role assignments can take time to propagate: an immediate 403 right after assigning a role does not automatically prove code is wrong.

### 4.2. Example of Assigning a Role with Azure CLI

Assuming you have the **principal object ID** of the managed identity (distinct from **client ID**) and the container resource ID. The operator running the command needs permission to create role assignments, such as Role Based Access Control Administrator or User Access Administrator at an appropriate scope:

~~~bash
STORAGE_ACCOUNT_ID="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>"
CONTAINER_SCOPE="$STORAGE_ACCOUNT_ID/blobServices/default/containers/documents"
MI_PRINCIPAL_ID="<managed-identity-principal-object-id>"

az role assignment create \
  --assignee-object-id "$MI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$CONTAINER_SCOPE"
~~~

This example illustrates **syntax and scope concepts**, not a command applied to any live account. The shell snippet uses Bash; on Windows PowerShell, adjust variable and line-continuation syntax accordingly. In real environments, grant permissions via IaC/Terraform/Bicep so changes can be reviewed and audited.

For services generating **user delegation keys**, the `Microsoft.Storage/storageAccounts/blobServices/generateUserDelegationKey/action` action must be permitted at a scope that covers it—typically the storage account, resource group, or subscription. Assigning a role solely on a single container may not suffice to request a user delegation key, even if the principal can read blobs in that container.

### 4.3. Azure Files-Specific Considerations

Azure Files offers multiple access methods that are not equivalent:

- **SMB:** identity-based authentication requires configuring an appropriate directory solution; authorization typically combines **share-level permissions** and directory/file ACLs. Never assign `Storage Blob Data Contributor` and expect SMB mounting to work.
- **NFS:** evaluate NFS security mechanisms, UNIX/POSIX permissions, network isolation, and file share tier requirements; do not assume NFS uses Entra OAuth RBAC like Blob.
- **REST/SDK:** has its own permission models and OAuth support depending on API version, operation type, and prerequisites; consult dedicated Azure Files documentation.

If the problem is simply storing/reading objects over APIs, Blob is usually the simpler choice. Choose File Share only when you need a filesystem and SMB/NFS semantics.

## 5. Identity Configuration in Spring Cloud Azure

### 5.1. Dependencies and Basic Configuration

Spring Cloud Azure provides starters for Azure Storage; example for an app using Blob and Queue:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
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
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

Select `spring-cloud-azure.version` according to the **Spring Boot compatibility table** for the Spring Cloud Azure release used by the project. Class names, starters, and auto-configuration properties can evolve across releases; verify against the guide for your chosen version before operating.

In `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
        queue:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  storage:
    documents-container: ${DOCUMENTS_CONTAINER:documents}
    jobs-queue: ${JOBS_QUEUE:document-jobs}
~~~

This example **declares no account keys, connection strings, or client secrets**. Credentials are resolved via Azure Identity/Spring Cloud Azure configuration and the runtime environment. For production using managed identity, configure it to select the exact identity assigned to the application.

### 5.2. Selecting Identity Across Multiple Environments

Some Spring Cloud Azure versions support configuring managed identity with properties like:

~~~yaml
# Only apply to Azure deployment profiles; verify against your version.
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: ${AZURE_CLIENT_ID}
~~~

- With **user-assigned managed identity**, `AZURE_CLIENT_ID` is the **client ID** of the identity attached to the host resource, not the principal object ID.
- With **system-assigned identity**, omit `client-id` if the framework/SDK defaults to the system-assigned identity.
- Do not force a local profile to use the managed identity endpoint outside Azure. Local runs should use a developer profile or credential chain.
- If auto-configuration is enabled, avoid manually defining duplicate client beans of the same type without clear intent.

In architectures requiring **explicit identity selection**, the Azure SDK provides a dedicated builder:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String account = System.getenv("AZURE_STORAGE_ACCOUNT_NAME");
String userAssignedClientId = System.getenv("AZURE_CLIENT_ID");
if (account == null || account.isBlank()) {
    throw new IllegalStateException("Missing AZURE_STORAGE_ACCOUNT_NAME");
}

ManagedIdentityCredentialBuilder credentialBuilder =
        new ManagedIdentityCredentialBuilder();
if (userAssignedClientId != null && !userAssignedClientId.isBlank()) {
    credentialBuilder.clientId(userAssignedClientId);
}
TokenCredential credential = credentialBuilder.build();

BlobServiceClient blobService = new BlobServiceClientBuilder()
        .endpoint("https://" + account + ".blob.core.windows.net")
        .credential(credential)
        .buildClient();
~~~

This Java snippet is for **when the app runs on a platform supporting managed identity** and needs direct Azure SDK configuration. It cannot authenticate via managed identity on ordinary local machines. For local development or controlled multi-source login, `DefaultAzureCredentialBuilder` is better suited; for production where you want to guarantee **only managed identity** is used, an explicit builder prevents the SDK from silently falling back to another credential source.

If using the SDK directly, include compatible `azure-identity` and `azure-storage-blob` libraries; do not create competing client configurations alongside the Spring Cloud Azure starter. In Azure sovereign clouds or custom-endpoint environments, URLs and authority settings must match the target cloud.

### 5.3. Connecting via SDK from Spring Boot

When starters auto-configure `BlobServiceClient` and `QueueServiceClient`, business code simply injects the clients:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueServiceClient;
import org.springframework.stereotype.Service;

@Service
public class StorageGateway {
    private final BlobServiceClient blobService;
    private final QueueServiceClient queueService;

    public StorageGateway(BlobServiceClient blobService,
                          QueueServiceClient queueService) {
        this.blobService = blobService;
        this.queueService = queueService;
    }

    public void putDocument(String blobName, byte[] smallPdf) {
        // Illustrates small data; large files should use streaming.
        var container = blobService.getBlobContainerClient("documents");
        var blob = container.getBlobClient(blobName);
        blob.upload(
                new java.io.ByteArrayInputStream(smallPdf),
                smallPdf.length,
                false);
    }

    public void enqueue(String blobName) {
        queueService.getQueueClient("document-jobs")
                .sendMessage(blobName);
    }
}
~~~

This code illustrates how clients share credentials to call Storage. Real applications must authenticate users, validate format/size, stream large files, handle already-existing blobs, ensure the queue is provisioned, and provide recovery if writing the Blob succeeds but enqueuing fails.

## 6. What Is a Shared Access Signature (SAS)?

A **SAS** is a signed access token specifying **resource, permissions, expiration**, and optional conditions such as start time, protocol, and IP range. Browsers or partners can send requests directly to Azure Storage using a SAS URL without holding the backend's account key or Entra token.

### 6.1. Three Types of SAS to Distinguish

| Type | Who Signs? | Scope/Methods | Key Point |
|---|---|---|---|
| **User delegation SAS** | User delegation key issued via Microsoft Entra ID | **Blob Storage** (and applicable ADLS Gen2 cases) | Preferred for Blob whenever possible; no account key needed for signing |
| **Service SAS** | Storage account key; can link to a stored access policy when supported | Resources of one storage service (Blob, Queue, Files, Table...) | Must protect the account key and understand revocation |
| **Account SAS** | Storage account key | Can grant broader service/resource type/operation scope | Does not support stored access policies; broad scope increases blast radius if leaked |

**User delegation SAS is not a universal SAS for Azure Queue or Azure Files.** When backend apps need Queue access, prefer Entra tokens/RBAC through the SDK instead of issuing account-key SAS tokens. For Azure Files, choose the appropriate SMB/REST mechanism and verify actual delegation capabilities.

### 6.2. How Do SAS and RBAC Roles Relate?

For a user delegation SAS, the key-requesting principal must be authorized by Azure to obtain a **user delegation key**. Access through the SAS also depends on the SAS parameters and delegated permissions under the service model. With a **service/account SAS signed by an account key**, the token holder exercises the permissions encoded in the valid token; the recipient does not need an RBAC role on their own Entra account.

Do not assume "a SAS signed with an account key is automatically bounded by the backend's RBAC like a user delegation SAS". An account key is highly privileged; if compromised, an attacker can sign SAS tokens with arbitrary permissions or access data directly via Shared Key within the account's limits.

### 6.3. SAS Example and Reading Its Scope

An illustrative URL (fake signature, **not valid**):

~~~text
https://storage-example.blob.core.windows.net/documents/contracts/a123.pdf
  ?sv=<api-version>
  &sr=b
  &sp=r
  &st=<start-time>
  &se=<expiry-time>
  &spr=https
  &sig=<signature>
~~~

- `sr=b`: the SAS targets a **blob**.
- `sp=r`: **read** permission only, excluding write/delete.
- `st` and `se`: validity window of the SAS, subject to clock skew and Azure validation rules.
- `spr=https`: enforces HTTPS-only usage.
- `sig`: cryptographic signature; never copy into logs, public tickets, or screenshots.

This example only explains the **general structure** of a SAS; exact parameters vary by SAS type, API version, and resource. Real SAS tokens are generated by the Azure SDK—never assemble and sign query strings manually.

## 7. Generating a User Delegation SAS to Read a Single Blob in Java

Scenario: the backend has verified `userId` is authorized to read a document, then generates a short-lived read-only URL for that exact blob. The backend holds a `BlobServiceClient` authenticated via **Microsoft Entra token**, not an account key.

### 7.1. Required Permissions

The backend identity needs:

1. Data-plane RBAC permission to **read the shared blob**, e.g., `Storage Blob Data Reader` on the appropriate container.
2. Permission to invoke `Microsoft.Storage/storageAccounts/blobServices/generateUserDelegationKey/action`, typically via **Storage Blob Delegator** at the storage account scope or an appropriate parent scope.
3. Allowed network connectivity to the Blob endpoint and accurate system time.

Common pitfall: an identity with Reader only on a **container** can still fail calling `getUserDelegationKey` because requesting the key requires a higher scope. Do not fix this by granting `Owner` at the subscription level; assign the exact required action/scope.

### 7.2. Service Example

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.UserDelegationKey;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import com.azure.storage.common.sas.SasProtocol;
import java.net.URI;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import org.springframework.stereotype.Service;

@Service
public class PrivateDocumentLinkService {
    private final BlobServiceClient blobService;

    public PrivateDocumentLinkService(BlobServiceClient blobService) {
        this.blobService = blobService;
    }

    public URI createReadLink(String authorizedBlobName) {
        // Caller has already verified the current user is allowed to read the document.
        BlobClient blob = blobService
                .getBlobContainerClient("documents")
                .getBlobClient(authorizedBlobName);

        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        OffsetDateTime starts = now.minusMinutes(5);
        OffsetDateTime expires = now.plusMinutes(10);

        // Principal must have generateUserDelegationKey permission.
        UserDelegationKey key =
                blobService.getUserDelegationKey(starts, expires);

        BlobSasPermission permission = new BlobSasPermission()
                .setReadPermission(true);
        BlobServiceSasSignatureValues values =
                new BlobServiceSasSignatureValues(expires, permission)
                        .setStartTime(starts)
                        .setProtocol(SasProtocol.HTTPS_ONLY);

        String sas = blob.generateUserDelegationSas(values, key);
        return URI.create(blob.getBlobUrl() + "?" + sas);
    }
}
~~~

This is a **URL-generating service**, not a public controller. Before calling `createReadLink`, the business layer must load the record by ID, verify owner/tenant and download policy, and ensure the blob resides in an allowed container. Never accept an arbitrary blob name from a client and sign URLs for any blob the backend identity can read.

The timestamps are examples. `starts = now − 5 minutes` mitigates clock skew errors, while `expires = now + 10 minutes` limits exposure. User delegation keys cannot exceed Azure's maximum lifetime (typically **7 days** max); individual SAS tokens can use shorter lifetimes. Under heavy traffic, consider **securely caching the user delegation key** within its valid window and reusing it to sign URLs rather than requesting a new key on every download, while still keeping SAS lifetimes short and rotating keys.

**Security note:** the output is a **URL containing a bearer credential**. Protect the URL from shared history, query-string logs, analytics tools, Referer headers, and unnecessary clipboard exposure; use HTTPS and appropriate `Cache-Control` headers on the backend. Once the SAS expires, the browser must request a fresh link after the backend re-verifies permissions.

### 7.3. SAS for Direct Uploads

For large files, the backend can generate a **random blob name** and issue a SAS permitting only **create/write** on that exact blob:

~~~java
BlobSasPermission uploadPermission = new BlobSasPermission()
        .setCreatePermission(true)
        .setWritePermission(true);
// Use this permission to build BlobServiceSasSignatureValues
// and call generateUserDelegationSas as in the read-only example above.
~~~

The `write` permission can allow modifying/overwriting within the resource scope, so verify the exact permissions granted, avoid reusing blob names with important data, and apply appropriate write conditions on the client. A SAS **does not automatically enforce business file size limits**; the backend must verify file size, content type, and scan files post-upload before marking them `READY`.

A secure flow:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Spring Boot API
    participant B as Azure Blob
    participant DB as Database
    U->>A: Request upload (authenticated, expected size)
    A->>DB: Create PENDING document + dedicated blobName
    A-->>U: Short-lived create/write SAS for exact blob
    U->>B: Upload directly over HTTPS
    B-->>U: Blob write result
    U->>A: Report completion
    A->>B: Verify blob size, metadata, status
    A->>DB: Transition to READY after verification
    A-->>U: Complete
~~~

## 8. Revoking, Rotating, and Governing SAS

### 8.1. Not Every SAS Can Be Revoked Individually Right Away

| Mechanism | Typical Expiration/Revocation Path | Key Consideration |
|---|---|---|
| Short-lived SAS | Reaches `expiry time` | Simplest way to bound risk |
| Service SAS linked to stored access policy (where supported) | Modify or delete the corresponding policy | Applies only when the service/resource supports this feature |
| Key-signed service/account SAS | Rotate the signing storage account key | Can affect multiple apps/SAS sharing the key; requires planning |
| User delegation SAS | SAS or delegation key expires; delegation keys can be revoked via Blob service mechanism | Revoking keys invalidates all SAS signed by those keys, not a single standalone URL |

**Account SAS does not support stored access policies.** **User delegation SAS also cannot bind a stored access policy** like service SAS. If business rules require "immediately revoking download access for a single user," consider proxying downloads through a backend API, maintaining authorization state in the application, or issuing very short-lived links; an already-issued, unexpired SAS does not re-check your application's user permissions database on every request.

### 8.2. Managing Account Keys

Account keys carry very broad privileges and can sign many kinds of SAS. Never place keys in source code, frontend variables, log files, or unnecessary CI/CD environments. Restrict the `listKeys` management-plane permission, audit key access, rotate on schedule, and isolate test/prod environments.

When supported by your workload, consider **disabling Shared Key authorization** to enforce data access via Microsoft Entra ID. **Assess compatibility before enabling**: Azure Files, certain APIs, or legacy apps have different account-key/SAS needs, and changing this setting can break existing clients.

### 8.3. SAS Guardrails

- Least-privilege permissions: `r` for download, minimal create/write permissions for upload; omit list/delete unless required.
- Minimal resource scope: a single specific blob is safer than a container-wide SAS when only one file is needed.
- Lifetime: just long enough for the task with reasonable clock-skew buffer; users request a new link after expiry.
- Protocol: HTTPS-only. Restrict IPs when client topology/addresses are stable; avoid breaking mobile users whose IPs roam.
- Audit at **SAS issuance time** with userId/documentId/expiry and correlation ID—**never log the SAS value**; combine with Storage logging when investigating access.

## 9. Secure Architecture for Blob + Queue

Suppose an API needs to store PDFs and trigger OCR jobs:

~~~mermaid
flowchart TB
    U[Authenticated Client] --> A[Spring Boot API]
    A -->|Managed identity + Blob Data Contributor| B[(Private Blob container)]
    A -->|Managed identity + Queue Message Sender| Q[(Storage Queue)]
    Q -->|Receive| W[OCR Worker]
    W -->|Queue Message Processor| Q
    W -->|Blob Data Reader| B
    U -->|Request document link| A
    A -->|Check permissions in DB| D[(Database)]
    A -->|Read-only user delegation SAS| U
    U -->|GET exact blob via HTTPS + SAS| B
~~~

Key decisions:

1. **Separate identities per service.** The API writes Blobs and sends Queue messages; the OCR worker reads Blobs and receives/deletes Queue messages. Each identity needs permissions only for its own job, rather than sharing `Storage Blob Data Contributor` and `Storage Queue Data Contributor`.
2. **Private containers.** Users have no default data-plane access; the backend checks business permissions before issuing a SAS or proxying the file.
3. **Large payloads in Blob; Queue holds only references.** Messages carry `documentId`/`blobName` and job ID, never the PDF; workers handle messages idempotently because Queue can redeliver messages.
4. **Track state.** Blob upload and Queue enqueue do not share a cross-service transaction; if Blob write succeeds but message send fails, use retries/reconciliation/outbox.
5. **Never share a single storage account key** across all microservices to bypass RBAC.

When using Azure Files, the permission architecture changes with SMB/NFS/REST protocols. Never reuse a Blob role pattern for services mounting shares.

## 10. Diagnosing Authentication and Authorization Errors

| Symptom | Likely Cause | How to Check |
|---|---|---|
| 401 Unauthorized | Missing/malformed token or invalid credential | Verify auth method, token audience, Azure Identity config |
| 403 AuthorizationPermissionMismatch | Valid token/SAS but missing action permission | Check data-plane RBAC, SAS `sp`, resource/scope |
| 403 calling `getUserDelegationKey` | Principal lacks `generateUserDelegationKey/action` at proper scope | Check Delegator role and storage account/parent scope |
| 403 due to Shared Key disabled | App still uses account key or key-based SAS where disallowed | Switch to Entra token/user delegation SAS where supported |
| 403 / connection failure with storage firewall | Endpoint network-restricted or private endpoint/DNS misconfigured | Check public network settings, private endpoint, DNS, firewall |
| Works locally, fails in production | Local uses developer identity; production uses a different principal | Confirm principal ID, role assignment, and propagation delay |
| User-assigned identity not selected | Confused **client ID** with **principal object ID** or identity not attached to host | Check resource identity configuration and SDK settings |
| SAS works on one machine but fails on another | SAS has IP restriction, clock skew, different network, or mangled URL | Check `st`/`se`/`spr`/`sip` and URL encoding |
| SAS can read but cannot upload/delete | SAS only grants `read`, missing permissions and resource type | Grant the right permission at the right scope |
| Azure Files SMB reports Access denied | Missing share-level permissions/ACLs or SMB auth misconfigured | Check identity provider, share role, NTFS ACLs, and mount context |

Never print tokens/SAS values to debug. Log request ID, operation, redacted resource names, safe principal info, and error codes. Note: 403 can stem from **data-plane RBAC**, **SAS**, **Shared Key policy**, or **networking**; inspect layer by layer instead of blindly granting broader roles.

### 10.1. Essential Deployment Checklist

~~~text
1. Does the Azure resource have managed identity enabled and properly attached?
2. Is the app intentionally selecting system-assigned or user-assigned identity?
3. Which principal object ID does Azure see when assigning the role?
4. Which data-plane role, at which scope, and has propagation completed?
5. Do the Blob/Queue/Files endpoints match the target cloud/account and DNS?
6. Does the storage firewall/private endpoint allow this workload?
7. Is any SAS signed with the right mechanism and valid lifetime/context?
8. Did the backend verify user authorization before accessing or issuing a link?
~~~

## 11. Integration Testing and Security Scenarios

### 11.1. What Are the Limits of Local Testing with Azurite?

**Azurite** is useful for testing Blob/Queue APIs and upload/download/enqueue logic locally. However, tests using the emulator connection string **cannot verify Microsoft Entra RBAC, managed identities, or production Azure private endpoints**. To validate real permissions, run tests against a dedicated integration-test Azure storage account using a principal/identity with least-privilege roles.

Never copy production account keys into emulator/test fixtures. Isolate test accounts and test data from production, clean up resources, and ensure tests cannot destroy real containers.

### 11.2. Test Matrix

| Test | Expected Result |
|---|---|
| Managed identity with Blob Data Reader | Can read blobs in allowed scope, cannot write/delete |
| Managed identity with Blob Data Contributor | Can upload blobs in assigned container, has no automatic access to other containers |
| Queue producer with only Message Sender | Can send messages; cannot receive/delete like a worker |
| Queue worker with only Message Processor | Can receive/process messages in granted scope; does not assume storage account admin rights |
| Principal without Blob Delegator | Creating user delegation key is denied even if it can read blobs |
| Short-lived single-blob SAS for read | Can GET exact blob; cannot write/delete or list outside scope |
| Expired or tampered-signature SAS | Request is rejected |
| SAS exposed after app revokes user access | Understand that unexpired SAS may still work; apply short lifetimes/revocation controls |
| Storage firewall blocks workload | Access denied even when RBAC is valid |
| Azure Files SMB missing ACL | Cannot open file even if share permissions look correct |
| User calls API for another tenant's document | Backend rejects **before** issuing a SAS |

For negative tests, use genuinely under-privileged identities instead of mocking `if (hasPermission)` in code; the goal is verifying IAM configuration and service behavior. Review logs and Azure activity/diagnostic logs to confirm roles/scopes, stripping SAS/tokens/secrets from telemetry.

### 11.3. Practice Exercises

**Scenario A — Image upload API:** The API runs on App Service and should only write Blobs to the `avatars` container. Choose the managed identity type, role, scope, and client authentication approach. Explain why no storage account key is needed.

**Scenario B — OCR Worker:** The API sends messages to a queue, and the worker receives and deletes messages. Separate two identities, pick two distinct roles to reduce permission scope, and explain the blast radius if the worker is compromised.

**Scenario C — 10-minute PDF link:** A user is authorized to read a contract. Describe how the backend checks permissions, retrieves a user delegation key, generates a read-only SAS, and avoids logging the URL. If the user's permission is revoked mid-session, what allows the old link to keep working, and how can design mitigate this?

**Scenario D — Legacy File Share:** A Windows app on a VM mounts Azure Files via SMB. An engineer assigns `Storage Blob Data Contributor` yet still gets Access denied. Explain why that role does not solve the issue and list the permission layers to verify in Azure Files SMB.

**Scenario E — Multi-cloud migration:** AWS typically uses IAM roles for workloads accessing S3, GCP uses service accounts/workload identity for Cloud Storage, and Azure uses managed identity/Entra RBAC for Blob. Compare them across the same four axes: workload identity, role/permission, short-lived credentials, and temporary access URL issuance. Do not assume IAM actions or URL-signing mechanisms are identical across providers.

## 12. Summary

Connecting securely to Azure Storage requires clearly defining **who is calling**, **what they are allowed to do**, and **which network path they take**. For Spring Boot on Azure, prefer **managed identity + Microsoft Entra ID + data-plane RBAC** so the SDK calls Blob/Queue without embedded secrets. For clients needing direct Blob operations, issue a **short-lived user delegation SAS** scoped to the exact resource and permissions after backend authorization checks. For **Azure Files**, evaluate SMB/NFS/REST access methods and their corresponding permission layers separately.

This mindset also underpins AWS and GCP storage integrations: always separate **workload identity**, **policy authorization**, **network control**, **temporary delegation**, **auditing**, and **real integration tests**. Library syntax and exact permissions vary by provider, but least privilege and short-lived credentials remain universally valuable.

### Official References

- [Microsoft Learn — Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Learn — Authorize access to Blob data with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Microsoft Learn — Assign an Azure role for access to blob data](https://learn.microsoft.com/azure/storage/blobs/assign-azure-role-data-access)
- [Microsoft Learn — Grant limited access to Azure Storage resources using shared access signatures](https://learn.microsoft.com/azure/storage/common/storage-sas-overview)
- [Microsoft Learn — Create a user delegation SAS for a blob with Java](https://learn.microsoft.com/azure/storage/blobs/storage-blob-user-delegation-sas-create-java)
- [Microsoft Learn — Authorize access to Azure Queue Storage using Microsoft Entra ID](https://learn.microsoft.com/azure/storage/queues/authorize-access-azure-active-directory)
- [Microsoft Learn — Azure Files identity-based authentication](https://learn.microsoft.com/azure/storage/files/storage-files-identity-auth-smb)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)

# DefaultAzureCredential and Choosing Identities Across Environments

When a Spring Boot application accesses Azure Blob Storage, Service Bus, Key Vault, or Cosmos DB, the first question is not simply "which key do I put in **application.yml**?". The application must know **which identity it is running as**, how that identity acquires tokens, and whether it has been granted permissions on the target resource.

**DefaultAzureCredential** from the **Azure Identity SDK for Java** provides a chain of credential sources suited for different development and deployment environments. As a result, much of the same Azure SDK calling code can run on a developer's machine, in CI, and on an Azure runtime. However, this convenience requires understanding how identity selection works so you do not accidentally use the wrong principal or exceed necessary privileges.

This lesson belongs to the **Azure Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing integrating Spring Boot with managed services across AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; focusing on identity and permissions, storage, messaging, data, secret management, integration testing, and evaluating differences between cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain **TokenCredential**, access tokens, and the role of **DefaultAzureCredential** in the Azure SDK for Java.
2. Distinguish user identity, service principal, system-assigned managed identity, user-assigned managed identity, and workload identity.
3. Choose an authentication approach for developer workstations, CI/CD, App Service/VMs/Functions, AKS, and non-Azure workloads.
4. Use the same Spring Boot architecture with **Spring Cloud Azure** or the **direct Azure SDK**, externalizing endpoints and identity selection into configuration.
5. Distinguish failures caused by **inability to acquire a token**, **acquiring a token for the wrong identity**, **missing Azure RBAC**, and **network/endpoint errors**.
6. Run integration tests with real identities without embedding client secrets, access keys, or tokens in source code.

## 2. Four Layers to Separate

Consider a **Documents API** application writing files to Azure Blob Storage:

~~~mermaid
flowchart LR
    A[Spring Boot Documents API] --> B[Azure SDK BlobServiceClient]
    B --> C[TokenCredential]
    C --> D[Microsoft Entra ID]
    B --> E[Blob Storage endpoint]
    F[Azure RBAC on storage account / container] -.-> E
    G[Firewall / VNet / Private Endpoint] -.-> E
~~~

The application succeeds when all four conditions align:

| Layer | Question | Example |
| --- | --- | --- |
| **Target** | Is the client calling the right resource? | **https://stexample.blob.core.windows.net** |
| **Authentication** | Can the credential acquire an appropriate token? | Managed identity, Azure CLI, workload identity |
| **Authorization** | Is the principal permitted to perform that operation? | **Storage Blob Data Contributor** role on the appropriate resource |
| **Network** | Can the runtime reach the endpoint under policy? | DNS, firewall, private endpoint, proxy, TLS |

**A valid token does not imply permission to write Blobs.** Likewise, having the right role assigned can still result in timeouts if the endpoint is wrong or private DNS is not functioning.

Some Azure SDKs also support **connection strings**, **shared keys**, or **SAS**. Those mechanisms have their own semantics and risks; this lesson prioritizes **Microsoft Entra tokens** via **TokenCredential** for identity-based access control.

## 3. What Are TokenCredential and DefaultAzureCredential?

**TokenCredential** is an abstraction in the Azure SDK that accepts a token request for one or more scopes and returns an access token upon successful authentication. SDK clients such as **BlobServiceClient** can use a **TokenCredential** without knowing login implementation details.

Common implementation types:

| Credential | Identity Source | When Appropriate |
| --- | --- | --- |
| **DefaultAzureCredential** | Tries a chain of supported credential sources | Development and shared configuration across environments, when credential sources are controlled |
| **AzureCliCredential** | Current developer's Azure CLI login session | Local tooling/labs, when explicitly selecting Azure CLI |
| **ManagedIdentityCredential** | Managed identity attached to a supported Azure resource | Azure runtimes, when wanting to force the managed identity login path |
| **WorkloadIdentityCredential** | OIDC trust federation between a workload and Entra ID | AKS or workloads with an appropriate federation mechanism |
| **EnvironmentCredential** | Environment variables for an SDK-supported authentication method | Environments with explicitly managed credentials; note risks of client secrets |
| **ClientSecretCredential** | Tenant ID, client ID, and client secret | Only when managed/workload identity cannot be used yet; must manage and rotate secrets securely |
| **ClientCertificateCredential** | Application certificate | Workloads with PKI and proper certificate lifecycle management |

**DefaultAzureCredential** combines several sources from the list above and potentially other IDE/CLI integrations. **The exact order, available sources, and rules for continuing or stopping when one source fails can change across Azure Identity SDK versions**. Therefore, do not copy a fixed order list from an older example and treat it as a long-term security contract.

### How Does the Credential Chain Select an Identity?

~~~mermaid
flowchart TD
    A[DefaultAzureCredential] --> B{Valid credential source available?}
    B -->|No| C[CredentialUnavailable / AuthenticationFailed]
    B -->|Yes| D[Acquire token for selected principal]
    D --> E[Azure SDK sends request to service]
    E --> F{Permitted on target resource?}
    F -->|Yes| G[Operation succeeds]
    F -->|No| H[401 / 403 or corresponding permission error]
~~~

This is a **conceptual diagram**. While probing sources, the SDK distinguishes an unavailable source from a source that attempted authentication and failed; fallback rules may depend on the SDK version and credential source type. Do not assume the SDK will always fall back to the Azure CLI after a deployment credential has attempted authentication and failed.

**Key point:** the credential chain does not evaluate "which identity has the most permissions" or "which identity matches the business environment" to pick one automatically. It operates strictly according to the configured order and conditions. The application must control which identities are allowed to be present.

## 4. Common Identity Types on Azure

### 4.1. User Identity on a Developer Workstation

A developer can sign in with **az login** or an IDE supported by Azure Identity. The Azure CLI caches the login session so **AzureCliCredential** can request tokens when needed.

Benefit: no need to issue a separate client secret per developer. However, developer permissions should be granted only on **test resources**, and production workloads must never depend on personal accounts.

### 4.2. Service Principal

A **service principal** is an application identity representation in a Microsoft Entra tenant. It has an **object/principal ID**, receives role assignments on resources, and can authenticate via secrets, certificates, or **federated credentials**.

Distinguish carefully:

- **Tenant ID:** the tenant issuing tokens / scoping the principal.
- **Client ID:** identifier of the application/identity selected for authentication.
- **Principal/Object ID:** the concrete object typically referenced when assigning or inspecting roles.
- **Client secret:** authentication secret, **not** the client ID, and should never appear in a repository.

A service principal using a client secret works, but introduces overhead for secret protection, rotation, and leak management. Whenever possible, prefer federation or managed identity.

### 4.3. System-Assigned Managed Identity

A **system-assigned managed identity** is tied to the lifecycle of an Azure resource that supports that identity type. Azure manages the underlying credentials, and the application obtains tokens through the runtime's managed identity mechanism; no client secret needs to be stored.

For example: an App Service has system-assigned identity enabled, and is then granted a Blob write role on the target storage account. If the resource is deleted, the system-assigned identity may be deleted along with it.

### 4.4. User-Assigned Managed Identity

A **user-assigned managed identity** is an independent Azure resource that can be attached to multiple supported resources. Its lifecycle is decoupled from individual workloads.

When a runtime has multiple identities or needs to specify an identity explicitly, the application can supply the **client ID** of the user-assigned managed identity. Do not confuse **client ID** with **principal ID** when selecting credentials or assigning roles.

**Note:** the existence of a managed identity does not mean every environment exposes a managed identity token endpoint; the identity must be attached to a supported runtime and the hosting service configuration must be verified.

### 4.5. Workload Identity Federation

**Federated workload identity** allows a workload holding a token from a trusted identity provider (typically OIDC) to exchange it for a Microsoft Entra access token, avoiding long-lived client secrets.

Two typical scenarios:

- **AKS with Microsoft Entra Workload ID:** a Kubernetes service account and federation configuration link the workload to an Entra application or user-assigned managed identity.
- **CI/CD such as GitHub Actions or Azure DevOps:** the job/pipeline identity is linked to Entra via trust and claims restricted to the appropriate repository/branch/environment.

This is a **federation** mechanism, not the same as letting every container automatically use the node/cluster's managed identity. You must match the issuer, subject, audience, service account, or pipeline identity to the actual token source.

## 5. Choosing an Identity by Environment

| Environment | Typically Preferred Option | Source in Azure Identity | Permissions & Risks to Control |
| --- | --- | --- | --- |
| **Developer workstation** | Developer account via Azure CLI/IDE | **DefaultAzureCredential** or **AzureCliCredential** | Grant access only to dev resources; watch out for leftover credential environment variables |
| **CI/CD with OIDC federation** | Service principal or managed identity configured with a federated credential | Workload federation, sometimes supplied to CLI by a CI login step | Restrict trust by repo/branch/environment; separate deployment permissions from data permissions |
| **App Service / Azure Functions** | System-assigned or user-assigned managed identity | **ManagedIdentityCredential** or DefaultAzureCredential | Assign data-plane roles on target resources, not just management permissions |
| **Azure VM / runtime supporting managed identity** | Managed identity attached to the runtime | **ManagedIdentityCredential** | Do not rely on Azure CLI or personal credential files in production |
| **AKS with Workload ID** | Workload identity federation via Kubernetes service account | **WorkloadIdentityCredential** or DefaultAzureCredential when configured accordingly | Verify service-account annotations, pod mutation, federated credentials, and roles |
| **Container/host outside Azure** | Federation if supported by the platform; otherwise organization-managed credentials | Credential suitable for the environment | Do not assume managed identity works automatically outside Azure |
| **Local automated tests** | Fake/mock credential for unit tests; lab identity for integration tests | Mock **TokenCredential** or lab environment credential | Isolate test resources; do not depend on personal accounts in CI |

**Selection principle:** prefer identities that do not store long-lived secrets; grant permissions at the **narrowest scope**; explicitly identify the principal for each environment.

### Should DefaultAzureCredential Be Used in Production?

It can be used if the environment is tightly controlled and you have verified which credential source is actually selected. However, for production workloads requiring a deterministic login path, using an explicit **ManagedIdentityCredential** or **WorkloadIdentityCredential** can reduce ambiguity.

**DefaultAzureCredential is not a mechanism that hard-locks an identity.** For example, a container accidentally carrying environment variables for a service principal can cause the chain to select a different credential than the intended managed identity. When policy demands a deterministic principal, select a specific credential or configure exclusions for disallowed sources using your SDK version's API.

## 6. Selecting Tenant, Subscription, and Principal

Before configuring credentials, avoid three common mix-ups:

1. **Tenant ID** identifies the Microsoft Entra identity space.
2. **Subscription ID** identifies the Azure Resource Manager governance/deployment/billing scope.
3. **Client ID** identifies the application or user-assigned identity to authenticate with.

For example, an application runs in subscription **app-prod**, while Blob Storage lives in subscription **data-prod**, yet both belong to the same tenant. The app's managed identity can still be assigned the **Storage Blob Data Contributor** role on the storage account in **data-prod**. In that case, the Blob SDK needs the **account endpoint + right credential + role + network**, without passing a subscription ID on each upload call.

Conversely, when using the Azure Resource Manager SDK to **create a storage account**, you must specify the subscription/resource group and hold the corresponding management-plane permissions.

**Cross-tenant interactions** require explicit access design and federation/delegation mechanisms; do not assume an identity in tenant A can call a data plane in tenant B simply by knowing the endpoint.

### Scoping by Role Assignment, Not Username

A role assignment typically binds:

~~~text
Principal (user/workload identity)
           +
Role definition (allowed permissions)
           +
Scope (management group / subscription / resource group / resource)
           =
Permissions applied within that scope
~~~

Some services have additional or separate data-plane authorization mechanisms; for instance, Azure Cosmos DB for NoSQL requires considering the service's own data-plane RBAC model. Thus, resource-management "Contributor" does not automatically mean permission to read every secret or write every Blob.

## 7. Hands-on Authentication on a Developer Machine

Assume a lab environment has tenant **11111111-1111-1111-1111-111111111111** and storage account **stexample**. The GUID and account name are illustrative only; replace them with real test values.

### 7.1. Signing In with Azure CLI

~~~bash
# Sign in with an account granted access to the dev tenant.
az login --tenant "11111111-1111-1111-1111-111111111111"

# View the tenant and subscription currently used by Azure CLI.
az account show --query "{tenant:tenantId, subscription:id, name:name}" --output json

# If you need to manage resources via CLI, specify the corresponding subscription.
az account set --subscription "<subscription-id>"
~~~

**az account set** changes the default subscription context for CLI/ARM commands; it does not alter a Blob hostname that was hard-coded or previously configured. When using **DefaultAzureCredential**, an IDE credential or environment variables may be selected ahead of the Azure CLI depending on the SDK version's chain. Therefore, **a successful az login does not prove the application is using the Azure CLI identity**.

### 7.2. Granting Test Permissions

Before uploading, an administrator or role-assignment owner must grant the data role at the right scope to the principal in use. For Blob write needs:

- Example role: **Storage Blob Data Contributor**.
- Scope: target container/account if supported by the role assignment model and operations; prefer the smallest scope.
- Network permissions: storage firewall/private endpoint must allow the dev runtime or test environment.

After assigning RBAC, there may be propagation delay. If the application still gets 403, verify the **actual principal** and detailed service error rather than merely checking that your personal account is signed in.

## 8. Configuring Azure SDK Directly in Spring Boot

Example: a Spring Boot 3.x application storing files in Blob Storage. Dependencies require **azure-identity** and **azure-storage-blob**, managed via a compatible BOM, alongside an appropriate Spring Boot starter for the application. The example focuses only on the identity/client configuration.

### 8.1. application.yml and Environment Variables

~~~yaml
app:
  azure:
    blob:
      endpoint: ${AZURE_BLOB_ENDPOINT}
      container: ${AZURE_BLOB_CONTAINER:documents}
~~~

Example environment variables:

~~~text
AZURE_BLOB_ENDPOINT=https://stexample.blob.core.windows.net
AZURE_BLOB_CONTAINER=documents
~~~

Endpoints contain no secrets. In Azure public cloud, an account's Blob endpoint typically follows **https://{account}.blob.core.windows.net**. In sovereign clouds, custom domains, or private networking, use the endpoint published by the service for the actual environment.

### 8.2. Creating TokenCredential and BlobServiceClient Beans

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AzureBlobConfiguration {

    @Bean
    public TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    public BlobServiceClient blobServiceClient(
            TokenCredential azureCredential,
            @Value("${app.azure.blob.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(azureCredential)
                .buildClient();
    }
}
~~~

With this code, the same **BlobServiceClient** calls the Azure SDK across different environments while **TokenCredential** handles token acquisition. Succeeding in creating the client does not confirm permissions: you must execute a test request against the service.

**Note when using a Spring Cloud Azure starter:** if the starter already auto-configures a **BlobServiceClient** or **TokenCredential** of the same type, defining additional beans can cause ambiguity or alter auto-configuration. Pick one clear client-creation mechanism, or declare intentional bean qualifiers/primary annotations.

### 8.3. Blob Operations Service

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorageService {

    private final BlobContainerClient containerClient;

    public DocumentStorageService(
            BlobServiceClient blobServiceClient,
            @Value("${app.azure.blob.container}") String containerName) {

        this.containerClient =
                blobServiceClient.getBlobContainerClient(containerName);
    }

    public void upload(String blobName, byte[] content) {
        containerClient.getBlobClient(blobName).upload(
                new ByteArrayInputStream(content), content.length, false);
    }
}
~~~

The example intentionally sets **overwrite=false** to avoid silently replacing existing content. In a real application, validate blob names, file sizes, MIME types, streaming reads, and end-user business authorization. The SDK client does not auto-create containers or grant RBAC.

**A Blob URL is not automatically a public URL.** For private containers, reading clients still need authentication or a securely issued authorization mechanism.

## 9. How Spring Cloud Azure Starters Auto-Configure Credentials

If the application already uses the **com.azure.spring:spring-cloud-azure-starter-storage-blob** starter, Spring Cloud Azure provides auto-configuration so the application can inject the SDK client. Typical configuration snippet:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

In Azure public cloud, the SDK/starter can derive the Blob endpoint from the account name under the appropriate version's defaults. For custom endpoints, sovereign clouds, emulators, or specialized identities, verify the **official configuration properties for your exact Spring Cloud Azure version**.

A Spring service can inject **BlobServiceClient**:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.stereotype.Service;

@Service
public class BlobHealthProbe {

    private final BlobServiceClient client;

    public BlobHealthProbe(BlobServiceClient client) {
        this.client = client;
    }

    public String endpoint() {
        return client.getAccountUrl();
    }
}
~~~

The method above only returns the configured endpoint to aid internal checks; it **does not test access permissions** and should not expose internal resource details on an unguarded public API.

**Relationship among the libraries:**

- **Spring Cloud Azure starter:** configures beans, property conventions, and Spring Boot integration.
- **Azure SDK for Java:** sends requests to Blob/Service Bus/Key Vault.
- **azure-identity:** acquires tokens via **TokenCredential**.
- **Microsoft Entra ID + Azure RBAC:** authenticates the principal and determines its permissions on the service.

It is not mandatory to declare every tenant/client ID property in application.yml if the runtime managed/workload identity already provides the correct details. Property names and auto-configuration mechanisms can change across Spring Cloud Azure lines, so consult version-specific documentation.

## 10. Managed Identity on App Service, Functions, and VMs

### 10.1. System-Assigned Identity

Logical steps:

1. Enable **system-assigned managed identity** on the Azure resource running the application (where supported by the service).
2. Note the identity's **principal ID**.
3. Assign the data role to the principal on the target resource, e.g., **Storage Blob Data Contributor** on the Blob Storage account/container.
4. Configure the correct Blob endpoint in Spring Boot.
5. Deploy the application and verify a real request using the workload identity.

In a system using only a single system-assigned identity on a supported runtime, **DefaultAzureCredential** can obtain a token via managed identity if higher-priority sources do not interfere. If you want to guarantee only managed identity is used, create an explicit credential bean:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

TokenCredential credential =
        new ManagedIdentityCredentialBuilder().build();
~~~

This is a credential instantiation snippet; in Spring Boot, expose it as a bean so clients can reuse it.

### 10.2. User-Assigned Identity

If the runtime has a user-assigned managed identity attached and needs to select the identity explicitly:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String managedIdentityClientId = System.getenv("AZURE_CLIENT_ID");

if (managedIdentityClientId == null ||
        managedIdentityClientId.isBlank()) {
    throw new IllegalStateException(
            "AZURE_CLIENT_ID is required for this user-assigned identity");
}

TokenCredential credential =
        new ManagedIdentityCredentialBuilder()
                .clientId(managedIdentityClientId)
                .build();
~~~

**AZURE_CLIENT_ID** here is the user-assigned identity's client ID, **not its principal ID**. The variable itself does not grant permissions; the identity must be attached to the runtime and hold roles on the target service.

With **DefaultAzureCredential**, Azure Identity also provides ways to select a user-assigned managed identity, such as builder options or environment variables depending on version. If the system has multiple identities, configure it explicitly to avoid picking the wrong principal.

## 11. Workload Identity on AKS

AKS Workload ID uses federation between a Kubernetes service account and Microsoft Entra. A typical flow includes:

~~~mermaid
sequenceDiagram
    participant P as Spring Boot Pod
    participant K as Kubernetes Service Account / OIDC
    participant E as Microsoft Entra ID
    participant S as Azure Storage
    P->>K: Receive projected service-account token
    P->>E: Exchange OIDC token via federated trust
    E-->>P: Access token for configured principal
    P->>S: HTTPS request + Entra access token
    S-->>P: Allow or deny per RBAC/policy
~~~

Values that must align:

| Component | Meaning |
| --- | --- |
| **Issuer** | OIDC token issuer for the AKS cluster |
| **Subject** | Specific Kubernetes service account being federated |
| **Audience** | Token audience configured for the federation flow |
| **Client ID** | Entra application or user-assigned managed identity receiving the token |
| **Tenant ID** | Tenant containing the corresponding Entra identity |
| **Federated credential** | Trust link binding issuer, subject, audience, and identity |
| **Azure data role** | Permissions for the principal on Blob, Service Bus, Key Vault, etc. |

In a properly configured AKS Workload ID setup, the pod can be injected with variables such as:

~~~text
AZURE_CLIENT_ID=<client-id-of-the-federated-identity>
AZURE_TENANT_ID=<tenant-id>
AZURE_FEDERATED_TOKEN_FILE=<path-to-projected-token>
~~~

These are **runtime variables**, not values to hard-code into the repository. The cluster must support an OIDC issuer, bind the right service account, and configure the pod so the token is projected. **DefaultAzureCredential** in Azure Identity versions supporting workload identity can consume those values; you can also use **WorkloadIdentityCredential** explicitly if policy requires it.

**Common failure:** the pod has the right service account but lacks a federated credential matching the issuer/subject/audience, or Entra issues a token yet the principal has no data role on the storage account. These two failures happen at different stages and require different checks.

## 12. CI/CD: Prefer Federation and Least Privilege

A pipeline may require two groups of permissions:

- **Deployment plane:** creating/updating the app or resources via ARM in a subscription/resource group.
- **Data plane:** reading/writing Blobs, sending/receiving Service Bus messages, or reading Key Vault secrets during integration tests.

If a pipeline only deploys artifacts, do not pre-grant it production Blob write permissions. Separate the **deployment identity** from the **runtime identity**; integration tests should use a test identity and dedicated test resources.

### CI Model with OIDC

1. The CI identity provider issues a token to the job after verifying repository/branch/environment conditions.
2. Entra has the corresponding federated credential configured.
3. The job exchanges the OIDC token for an Azure access token via a mechanism supported by the CI tooling/SDK.
4. Deployment tasks or integration tests use the token within the granted permission scope.
5. Avoid storing static client secrets in CI environment variables when federation satisfies the requirement.

**An Azure Login action/task does not mean DefaultAzureCredential inside a Java application automatically picks up every CI context.** If the pipeline runs JVM integration tests, verify which credential source the Java SDK actually sees: an Azure CLI session on the runner, a workload token file, or another supplied credential. Also ensure that source matches the target environment and token lifetime.

### Environment Variables: Useful Yet Can Cause Wrong Identity Selection

Some standard Azure Identity configurations include:

| Variable | Typical Function |
| --- | --- |
| **AZURE_TENANT_ID** | Specifies the tenant for applicable credentials |
| **AZURE_CLIENT_ID** | Specifies the client application or user-assigned identity depending on the credential mechanism |
| **AZURE_CLIENT_SECRET** | Secret for service-principal configuration using client-secret flow |
| **AZURE_FEDERATED_TOKEN_FILE** | Path to the OIDC token file for workload identity |
| **AZURE_AUTHORITY_HOST** | Specifies the authority host in supported cloud environments |

A single variable does not necessarily activate an entire credential. However, a **complete configuration set** for a higher-priority source can change which principal **DefaultAzureCredential** selects.

Avoid copying examples containing **AZURE_CLIENT_SECRET** into production configurations if you are using managed identity or federation. In Kubernetes, do not treat an environment-variable secret as a long-term identity management solution.

## 13. Selecting an Explicit Credential When Determinism Matters

One organizational pattern is deciding the **identity mode** at the deployment layer:

| Identity mode | Suitable Environment | Java Credential |
| --- | --- | --- |
| **developer** | Personal workstation or lab | AzureCliCredential if wanting to force Azure CLI |
| **managed-identity** | App Service, Functions, VMs, etc. | ManagedIdentityCredential |
| **workload-identity** | AKS / OIDC federation | WorkloadIdentityCredential |
| **default** | Environments with controlled credential chain | DefaultAzureCredential |

Example of a simple factory driven by a configuration profile:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.AzureCliCredentialBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.identity.ManagedIdentityCredentialBuilder;

public final class IdentitySelector {

    private IdentitySelector() {}

    public static TokenCredential choose(
            String mode, String managedIdentityClientId) {

        switch (mode) {
            case "developer":
                return new AzureCliCredentialBuilder().build();

            case "managed-identity":
                if (managedIdentityClientId != null &&
                        !managedIdentityClientId.isBlank()) {
                    return new ManagedIdentityCredentialBuilder()
                            .clientId(managedIdentityClientId)
                            .build();
                }
                return new ManagedIdentityCredentialBuilder().build();

            case "default":
                return new DefaultAzureCredentialBuilder().build();

            default:
                throw new IllegalArgumentException(
                        "Unsupported Azure identity mode: " + mode);
        }
    }
}
~~~

This is an **illustration of explicit credential selection**, not a mandatory library pattern. A **workload-identity** mode can be added with **WorkloadIdentityCredentialBuilder** after confirming tenant/client ID, token file, and SDK version support. Never use simulated modes to switch identities in production runtime based on an end-user request.

**Benefit:** production can fail fast if managed identity has not been provisioned, instead of unexpectedly picking up developer credentials or credentials from another source.

## 14. Per-Service RBAC and Limits of Credentials

A credential obtains a token for an identity, while the **target service** checks which operations are allowed.

| Use Case | Service | Example Permission |
| --- | --- | --- |
| Upload/write Blob | Azure Blob Storage | **Storage Blob Data Contributor** |
| Read private Blob | Azure Blob Storage | **Storage Blob Data Reader** |
| Send messages | Azure Service Bus | **Azure Service Bus Data Sender** |
| Receive messages | Azure Service Bus | **Azure Service Bus Data Receiver** |
| Read secrets (vault using Azure RBAC model) | Azure Key Vault | **Key Vault Secrets User** |
| Manipulate Cosmos DB for NoSQL data | Azure Cosmos DB | Corresponding data role in Cosmos DB data-plane RBAC |

This list provides **directional examples**, not a substitute for checking exact scopes/permissions and each service's own authorization model. Key Vault also supports an access policy model on some resources; verify the vault's permission model.

**The same credential can be used across multiple Azure services**. Each SDK client requests an appropriate token for its service. However, the principal still needs distinct roles on each respective endpoint/resource.

### Workload Permissions Are Not Business-User Permissions

If the Documents API uses a managed identity with permission to write Blobs, that permission belongs to the **application**. Callers hitting the Documents API's HTTP endpoint are not automatically granted the corresponding Azure RBAC permissions. The application must verify the **business user's** authentication/authorization before acting on their behalf.

This is why **workload identity** must be distinguished from **end-user identity**. Using a service identity to access resources is usually appropriate for a backend, but it does not replace API-layer authorization checks.

## 15. Testing and Observing Real Identities

### 15.1. Unit Tests

The goal of unit tests is to verify business logic when the Azure SDK returns success, 403, timeout, or conflict, **without requiring real Azure tokens or resources**. You can inject an adapter around BlobServiceClient and mock the adapter, or mock the SDK client as fits your architecture.

If code instantiates credentials inside every business method, unit testing becomes harder to control; inject **TokenCredential** and clients as Spring beans as needed.

### 15.2. Local Integration Tests

**Azurite** can emulate part of Azure Storage, making it useful for testing supported Blob APIs. However, Azurite **cannot replace testing real Microsoft Entra ID, managed identity, or Azure RBAC**. When using the emulator, credential/endpoint configuration can differ markedly from a live Azure environment.

### 15.3. Integration Tests on Azure Test Resources

You need at least one test featuring:

1. A test identity supplied by the CI/runtime environment.
2. A data role at the right scope, allowing time for the role assignment to propagate.
3. The real endpoint and DNS of the test resource.
4. A low-impact operation, such as creating a randomly named blob and then deleting it.
5. Cleanup and inspection of error codes/request IDs, without affecting production data.

**Do not just test whether the Spring context starts.** Many Azure clients are constructed without calling the service; credential or RBAC errors only surface on the first request that requires an access token or hits the endpoint.

### 15.4. Safe Logging

When investigating which source the credential chain is using, enable **azure-identity / Azure SDK** diagnostic logging per your version's guide and use an appropriate log level in test environments. You can observe:

- Which credential sources are available or failing.
- Error categories and causes (e.g., no managed identity endpoint present).
- Endpoint hostname, operation, HTTP status, and Azure request/correlation ID.
- Tenant/client ID or principal identity **only when permitted in internal logs**, with appropriate masking.

**Never log access tokens, refresh tokens, secrets, connection strings, SAS URLs, or federation token file contents**. Likewise, do not dump all environment variables, as they may contain non-Azure secrets.

## 16. Troubleshooting DefaultAzureCredential Errors

| Symptom | Suspect Area | First Check |
| --- | --- | --- |
| **CredentialUnavailableException** | No suitable credential source or source not ready | Inspect credential chain, runtime environment, managed/workload identity settings |
| **AuthenticationFailedException** | A credential source attempted authentication and failed | Check tenant, issuer/federated credential, secret/certificate if used, and SDK diagnostics |
| Works locally, fails on deployment | Runtime lacks the laptop's Azure CLI/IDE session | Enable managed identity or configure workload federation on the runtime |
| Runtime uses the wrong identity | Credential env vars, multiple user-assigned identities, or higher-priority source | Identify the selected principal; use an explicit credential when needed |
| Acquires token yet Blob returns **403** | Data-plane RBAC, wrong scope, or network policy | Check roles on the **exact storage account/container**, check network policy |
| Key Vault returns **403** | Secret read permission, permission model, principal, or vault URI | Check Key Vault RBAC/access policy and tenant, not just ARM Reader |
| Service Bus rejects sender/receiver | Wrong namespace/entity, missing send/receive role, or network | Check namespace, queue/topic, Data Sender/Receiver role |
| **401** from service | Invalid token or not issued for the right endpoint/audience | Verify SDK/service target, authority, and credential chain |
| Timeout on Azure runtime | Private DNS, firewall, outbound route, proxy | Check DNS and reachability from inside the container/VM/pod |
| Connects to right Azure resource, yet local CLI sees another | CLI points to a different subscription or CLI is not the source the SDK chose | Check CLI context and the account/endpoint configured in the app |

### Ordered Troubleshooting Workflow

~~~mermaid
flowchart TD
    A[App call to Azure fails] --> B{Access token acquired?}
    B -->|No| C[Check credential source / tenant / federation]
    B -->|Yes| D{Request hitting right endpoint?}
    D -->|No| E[Fix account / namespace / DNS / SDK config]
    D -->|Yes| F{401 or 403 returned?}
    F -->|Yes| G[Check audience, principal, role, network policy]
    F -->|No| H[Check timeout, quota, retry, operation semantics]
~~~

Always inspect the **root cause** and actual service details. For instance, a 403 error can come from Storage authorization or a network rule; do not assume every 403 means a missing role.

## 17. Comparing with AWS and Google Cloud

All three clouds have mechanisms to acquire credentials from the runtime environment, though their identity models and APIs differ:

| Need | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Default credential chain | **DefaultAzureCredential** | **DefaultCredentialsProvider** in AWS SDK for Java v2 | **Application Default Credentials (ADC)** |
| Cloud workload identity | Managed identity / federated workload identity | IAM role and temporary credentials via metadata/STS | Service account / Workload Identity Federation |
| On developer workstation | Azure CLI/IDE or supported credentials | AWS profile/SSO or supported credential sources | gcloud ADC or supported credential sources |
| Data permissions | Azure RBAC and per-service authorization | IAM policies, resource policies | Cloud IAM and per-resource permissions |
| Reducing long-lived secrets in CI | OIDC federation with Microsoft Entra | OIDC federation / STS AssumeRole as appropriate | Workload Identity Federation |

**Do not copy environment variables directly between clouds.** While they share the "credential chain" concept, source ordering, principal selection, audiences, and authorization models differ. When building multi-cloud integrations, place identity/client creation behind provider-specific adapters and define least-privilege permissions per service.

## 18. Lab Exercise: One Application, Three Environments

**Problem:** Spring Boot Documents API stores files into a private Blob container **documents**. Use a single business layer and deploy it in three different environments.

**Environment A — developer workstation:**

1. Sign in with Azure CLI to the dev tenant.
2. Assign **Storage Blob Data Contributor** to the dev account on the lab storage account.
3. Configure the endpoint via an environment variable and run the application with **DefaultAzureCredential**.
4. Verify the actual resource written to and the credential source via safe SDK diagnostics.

**Environment B — Azure App Service:**

1. Enable managed identity for the App Service.
2. Grant the Blob write role to the **App Service principal**, not a personal account.
3. Deploy the same code, configure the account endpoint, and test uploading.
4. Temporarily revoke the write permission on the test resource and observe the 403 response; restore the role to complete the lab.

**Environment C — AKS Workload ID or OIDC-enabled CI:**

1. Set up the matching issuer, subject, audience, and federated credential.
2. Configure the service account/pipeline so the workload receives a projected token.
3. Grant the role on the test storage account to the federated principal.
4. Run the integration test without a static client secret.
5. Confirm the exact credential source and role via appropriate logs/diagnostics.

**Deliverable:** a table covering the three environments with **principal ID/client ID (without secrets)**, credential mechanism, RBAC scope, Blob endpoint, pass/fail test results, and pipeline reproduction steps.

### Self-Check Questions

1. Why does **DefaultAzureCredential** work on a laptop yet fail automatically inside a bare container?
2. Can **client ID** and **principal ID** be used interchangeably in every situation?
3. Why does a successful **az login** not prove that the Azure SDK is using the Azure CLI credential?
4. When is an explicit **ManagedIdentityCredential** more appropriate than a multi-source credential chain?
5. Which issuer/subject/audience components must match for workload identity federation?
6. Why might an account with permission to create a storage account via ARM still be unable to upload a Blob?
7. Does testing with Azurite prove that RBAC and managed identity are configured properly?
8. When receiving **403**, why must you inspect **principal, RBAC scope, and network policy** together?

## 19. Key Takeaways

- **DefaultAzureCredential** helps the SDK find a token source based on the environment; it **does not decide which principal fits the business context**, does not grant permissions, and does not create Azure resources.
- For dev, use developer identities on test resources; for Azure runtimes, prefer **managed identity**; for AKS/CI or federation-capable hosts, prefer **workload identity federation** when appropriate.
- Specify an explicit credential when production requires determinism. **Client ID, principal ID, and tenant ID** have distinct meanings.
- For a request to succeed, you need **the right endpoint, the right identity, data-plane permissions, and a valid network path**. Spring Cloud Azure starters help configure clients, Azure Identity acquires tokens, and Azure RBAC/service policies govern authorization.
- Test at least one real request in the target environment; inspect the credential source safely and never log tokens or secrets.

## References

- [DefaultAzureCredential in Azure Identity for Java](https://learn.microsoft.com/java/api/com.azure.identity.defaultazurecredential)
- [Authentication with Azure Identity client library for Java](https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview)
- [Azure Managed Identity overview](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Entra Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure RBAC overview](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)

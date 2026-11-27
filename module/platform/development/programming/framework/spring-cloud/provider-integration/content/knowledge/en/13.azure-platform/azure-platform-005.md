# Azure CLI, Managed Identity, and Workload Identity

During Spring Boot development with Azure, the same feature can run successfully on a developer's laptop yet fail after deployment to App Service, AKS, or a CI pipeline. A common reason is that **the identity source changes by environment**: a laptop uses an **Azure CLI** login session, an app running on Azure can use a **managed identity**, and a Pod on AKS or a CI job is typically suited for **workload identity federation**.

This lesson belongs to the **Azure Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, practicing integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries. The topic focuses on configuring and verifying Azure identities for accessing storage, messaging, data, and secrets, while laying the groundwork for integration testing and comparing permission models across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Use the **Azure CLI** to verify tenant, subscription, principal, resources, and permissions in a development environment.
2. Distinguish **system-assigned managed identity**, **user-assigned managed identity**, service principal, and workload identity federation.
3. Enable managed identity for an Azure workload and grant data-plane permissions to the right principal and scope.
4. Describe the setup workflow for **Microsoft Entra Workload ID** on AKS: OIDC issuer, federated credential, Kubernetes service account, and Pod.
5. Choose **AzureCliCredential**, **ManagedIdentityCredential**, **WorkloadIdentityCredential**, or **DefaultAzureCredential** in Spring Boot based on runtime conditions.
6. Diagnose authentication, authorization, and networking errors; design safe integration tests per environment.

## 2. Three Tools, Three Responsibilities to Distinguish

| Component | What Does It Provide? | Typical Usage Location | What It Does Not Do Automatically |
| --- | --- | --- | --- |
| **Azure CLI** | Tool for running Azure commands and signing in to tenants and subscriptions | Developer machines, admin terminals, authorized pipelines | Does not automatically grant permissions to a Spring Boot app running elsewhere |
| **Managed identity** | Azure-managed workload identity attached to a supported Azure resource | App Service, Functions, VMs, and supported services | Does not automatically grant Blob write, message send, or secret read permissions |
| **Workload identity federation** | Bridges tokens from a trusted workload/identity provider with Microsoft Entra | AKS Workload ID, OIDC-enabled CI/CD | Does not automatically choose the right namespace/service account or Azure RBAC |

An application-side layer is also needed: **Azure Identity SDK for Java**, which provides **TokenCredential** implementations. In a Spring Boot application, Azure SDK clients use tokens from this credential when calling services.

~~~mermaid
flowchart LR
    L[Dev machine / Azure CLI] --> C[AzureCliCredential]
    M[App Service / VM] --> D[ManagedIdentityCredential]
    W[AKS / OIDC token] --> E[WorkloadIdentityCredential]
    C --> SDK[Azure SDK client]
    D --> SDK
    E --> SDK
    SDK --> S[Blob / Service Bus / Key Vault]
    R[RBAC / policy] -. controls access .-> S
~~~

**Authentication** proves who the workload or user is; **authorization** decides which operations are permitted; **network reachability** decides whether requests can reach the endpoint. All three conditions must be verified independently.

## 3. Identifiers That Must Not Be Confused

Suppose a system has a Spring Boot service that needs to access Azure Blob Storage:

| Value | Meaning | Example Usage |
| --- | --- | --- |
| **Tenant ID** | Microsoft Entra directory identifier | Issuing tokens and configuring federation |
| **Subscription ID** | ARM resource management, billing, and governance unit | Creating App Service, Storage Account, Azure RBAC scope |
| **Resource group** | Logical grouping within a subscription | Locating App Service, identity, Storage Account |
| **Client ID** | Identifier of an application or user-assigned identity | Selecting a user-assigned managed identity |
| **Principal/Object ID** | Identifier of the service principal/object granted permissions | Creating an Azure role assignment |
| **Resource ID** | ARM path identifying a resource | Specifying RBAC scope or attaching an identity |
| **Service endpoint** | Host/URL for the SDK to communicate with the data service | Blob, Service Bus, or Key Vault address |

In most **Blob data-plane** calls, the application needs the **Blob endpoint + credential + data permissions**; it does not pass a subscription ID in every upload call. Subscription and resource group become important when managing resources, assigning permissions, or locating the right account.

A user-assigned managed identity has a **client ID**, a **principal ID**, and a **resource ID**. These three values are not interchangeable.

## 4. Azure CLI on a Developer Workstation

Azure CLI is a tool for managing resources and establishing a session with Microsoft Entra. It is useful for cross-checking dev environment settings before running a Spring Boot application.

### 4.1. Signing In and Inspecting Context

~~~bash
# Sign in interactively using a developer identity.
az login

# If the organization requires a specific tenant:
az login --tenant "<tenant-id>"

# View the subscriptions accessible to the current identity.
az account list --output table

# View the default tenant and subscription.
az account show   --query "{tenant:tenantId, subscription:id, name:name}"   --output json

# Switch the default subscription for subsequent CLI operations.
az account set --subscription "<subscription-id>"
~~~

**az account set** selects the subscription context for the Azure CLI; it does not grant new permissions, does not change the tenant for every client, and does not change the endpoint of an already-created **BlobServiceClient**.

A developer workstation may have multiple credential sources coexisting: Azure CLI, IDE, service principal environment variables, or other tools. **DefaultAzureCredential** does not necessarily select Azure CLI just because the developer ran **az login**. When you want to test the CLI session specifically, select **AzureCliCredential** explicitly.

### 4.2. Verifying the Target Resource

~~~bash
# Read management information for the storage account.
az storage account show   --name "<storage-account-name>"   --resource-group "<resource-group-name>"   --query "{id:id, name:name, location:location, endpoints:primaryEndpoints}"   --output json
~~~

This command uses **management-plane** permissions to read the resource. The result includes the **resource ID** and endpoints; it does not yet prove the user can read/write Blob data.

To test the data plane using the Azure CLI login token:

~~~bash
# The container must exist; account and data permissions must be valid.
az storage blob list   --account-name "<storage-account-name>"   --container-name "<container-name>"   --auth-mode login   --output table
~~~

Depending on the operation, appropriate data-plane permissions are required, such as **Storage Blob Data Reader** for reading or **Storage Blob Data Contributor** for writing. Someone with the **Contributor** role on the management plane does not automatically have permission to read blobs.

### 4.3. When Not to Use Azure CLI

Never use a personal login account as the permanent authentication mechanism for a production service. Servers should not depend on an **az login** cache, a developer's MFA session, or manual re-login after a restart.

**Azure CLI can still be present in a pipeline**, provided the pipeline signs in through a properly managed identity and the Java SDK actually uses the intended credential source. Running **az login** in CI does not mean every JVM process automatically receives a **WorkloadIdentityCredential**.

## 5. Managed Identity: Concept and Two Types

A **managed identity** is an identity managed by Azure so that supported Azure workloads can acquire Microsoft Entra access tokens without storing long-lived client secrets themselves.

| Criterion | System-assigned | User-assigned |
| --- | --- | --- |
| Management unit | Identity attached directly to a single supported resource | A standalone Azure identity resource |
| Lifecycle | Tied to the resource; deleting the resource removes the attached identity | Exists independently and can be reused |
| Reuse across workloads | Not the primary purpose | Can be attached to multiple supported resources |
| Selecting identity at runtime | Usually works by default when only that identity applies | Should pass client ID/resource ID per API to pick the right identity |
| Access to other resources | Requires appropriate role assignments | Requires appropriate role assignments |

A managed identity **is not an alias for a subscription**: the same managed identity can be granted roles on target resources in another subscription if the identity and permission model permits it.

## 6. Creating a Managed Identity and Attaching It to a Workload

### 6.1. Enabling System-Assigned Identity for App Service

Suppose a Spring Boot service is deployed to Azure App Service. A user with resource management permissions can enable the identity:

~~~bash
az webapp identity assign   --resource-group "<app-resource-group>"   --name "<app-service-name>"
~~~

The command returns or enables querying the identity details. You can read the principal ID:

~~~bash
az webapp identity show   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --query "{principalId:principalId, tenantId:tenantId, type:type}"   --output json
~~~

**Principal ID** is the identifier used when assigning permissions to the identity. The App Service must genuinely support managed identity and have it enabled before the SDK inside the application can acquire tokens.

### 6.2. Creating a User-Assigned Managed Identity

~~~bash
az identity create   --resource-group "<identity-resource-group>"   --name "<user-assigned-identity-name>"

az identity show   --resource-group "<identity-resource-group>"   --name "<user-assigned-identity-name>"   --query "{id:id, clientId:clientId, principalId:principalId, tenantId:tenantId}"   --output json
~~~

The output includes:

- **id:** resource ID of the identity, used when referencing this resource.
- **clientId:** used to select the user-assigned identity in certain credentials/runtimes.
- **principalId:** used when assigning Azure RBAC permissions.
- **tenantId:** tenant managing the identity.

You can attach a user-assigned identity to an App Service using the identity's resource ID, if supported by the service and admin permissions:

~~~bash
az webapp identity assign   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --identities "<user-assigned-identity-resource-id>"
~~~

Creating an identity or attaching it to an App Service does not automatically grant data permissions for Blob, Service Bus, or Key Vault.

### 6.3. Selecting a User-Assigned Identity in Java

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String clientId = System.getenv("AZURE_CLIENT_ID");
if (clientId == null || clientId.isBlank()) {
    throw new IllegalStateException("AZURE_CLIENT_ID is required");
}

TokenCredential credential = new ManagedIdentityCredentialBuilder()
        .clientId(clientId)
        .build();
~~~

**AZURE_CLIENT_ID** must be the **client ID** of the user-assigned managed identity attached to the runtime. If the project wants to use a system-assigned identity, it can instantiate **new ManagedIdentityCredentialBuilder().build()** in a supported environment.

Do not configure a client ID and assume that identity can be selected on just any machine or Pod. **ManagedIdentityCredential** requires the supporting Azure hosting service's token-issuing infrastructure with that identity attached.

## 7. Granting Data Permissions to a Managed Identity

Suppose App Service needs to upload Blobs into a storage account. You need to identify:

1. The managed identity's principal ID.
2. The storage account's resource ID or a narrower scope supported by role assignment.
3. The role for data operations, e.g., **Storage Blob Data Contributor**.
4. The person/command creating the role assignment must hold **role-assignment management permissions** at the corresponding scope.

From an authorized admin terminal:

~~~bash
# Assign the role to the principal ID, do not use the client ID here.
az role assignment create   --assignee-object-id "<managed-identity-principal-id>"   --assignee-principal-type ServicePrincipal   --role "Storage Blob Data Contributor"   --scope "<storage-account-resource-id>"
~~~

For example, **storage-account-resource-id** looks like:

~~~text
/subscriptions/<subscription-id>/resourceGroups/<rg-name>/providers/Microsoft.Storage/storageAccounts/<account-name>
~~~

Role assignments may take time to propagate. If requests still fail right after granting permissions, check propagation delay, scope, actual principal, and the service response before retrying in a controlled manner.

**Authorization principle:** do not grant subscription-wide **Owner/Contributor** just so one service can write blobs. An application may need **Storage Blob Data Contributor** on a test storage account and **Azure Service Bus Data Sender** on a designated namespace/queue, without needing management permissions across all resources.

### Checking Role Assignments

~~~bash
az role assignment list   --assignee "<managed-identity-principal-id>"   --scope "<storage-account-resource-id>"   --include-inherited   --output table
~~~

Cross-check the output against the actual scope and role. Permissions may be granted at a parent scope or via a service-specific mechanism. For Azure Cosmos DB for NoSQL, data-plane authorization requires analyzing Cosmos DB's dedicated role model rather than inferring all permissions from resource-management Azure RBAC.

## 8. How Managed Identity Works Inside Spring Boot

In an Azure runtime, the Azure Identity SDK uses the managed identity mechanism provided by the platform to fetch tokens. The SDK calls the environment's appropriate endpoint/token broker automatically; the application does not manually query metadata endpoints or parse tokens.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot app
    participant C as ManagedIdentityCredential
    participant M as Azure managed identity endpoint
    participant S as Blob Storage
    A->>C: Request token for Storage
    C->>M: Request token for runtime-attached identity
    M-->>C: Access token
    C-->>A: TokenCredential supplies token
    A->>S: Upload blob via HTTPS + token
    S-->>A: Allow or deny per RBAC/policy
~~~

### 8.1. Spring Cloud Azure Configuration

With a **com.azure.spring:spring-cloud-azure-starter-storage-blob** starter compatible with your Spring Boot version, basic configuration can be:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

Example of an application injecting the auto-configured **BlobServiceClient**:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobContainerClient;
import org.springframework.stereotype.Service;

@Service
public class BlobContainerLocator {

    private final BlobServiceClient blobServiceClient;

    public BlobContainerLocator(BlobServiceClient blobServiceClient) {
        this.blobServiceClient = blobServiceClient;
    }

    public BlobContainerClient documents() {
        return blobServiceClient.getBlobContainerClient("documents");
    }
}
~~~

This is a **data-access** example, not creating an Azure storage account or assigning roles. When the starter uses the default credential chain for its version, managed identity is chosen if the environment provides an appropriate identity and no other credential sources override the choice.

If you want to enforce a specific identity, configure credentials/beans according to the **Spring Cloud Azure version** in use. Avoid simultaneously defining a manual **BlobServiceClient** of the same type when the starter already auto-configures one, unless bean design is handled explicitly.

### 8.2. Direct Azure SDK Configuration

Without the starter, the application can manage the SDK client as a Spring bean:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BlobClientConfiguration {

    @Bean
    public TokenCredential managedIdentityCredential(
            @Value("${app.azure.identity.client-id:}") String clientId) {

        ManagedIdentityCredentialBuilder builder =
                new ManagedIdentityCredentialBuilder();

        if (!clientId.isBlank()) {
            builder.clientId(clientId);
        }
        return builder.build();
    }

    @Bean
    public BlobServiceClient blobServiceClient(
            TokenCredential managedIdentityCredential,
            @Value("${app.azure.blob.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(managedIdentityCredential)
                .buildClient();
    }
}
~~~

Configuration file:

~~~yaml
app:
  azure:
    identity:
      client-id: ${AZURE_CLIENT_ID:}
    blob:
      endpoint: ${AZURE_BLOB_ENDPOINT}
~~~

Leave **client-id** empty if using a system-assigned managed identity in a compatible runtime. For a user-assigned identity, provide the exact client ID of the attached identity. The Blob endpoint is the target address and may belong to a different subscription than the app's runtime subscription; permissions remain tied to the identity on the target resource.

## 9. What Is Workload Identity Federation?

**Workload identity federation** solves this problem: a workload running in Kubernetes or a CI system already holds identity proof from a trusted identity provider; how can the workload access Azure without storing a long-lived client secret?

Microsoft Entra establishes a **federated identity credential** attached to a supported application or identity, specifying the trusted **issuer, subject, and audience**. The workload receives a token from the issuer and uses it as proof to exchange for an Azure access token for the configured principal.

~~~mermaid
sequenceDiagram
    participant W as AKS Pod / CI job
    participant O as OIDC issuer
    participant E as Microsoft Entra ID
    participant A as Azure managed service
    W->>O: Receive OIDC token from environment
    W->>E: Exchange OIDC token via federated trust
    E-->>W: Access token for linked identity
    W->>A: Azure SDK request with access token
    A-->>W: Evaluate RBAC / policy and return result
~~~

Three federation attributes must **match exactly**:

| Attribute | Meaning | AKS Example |
| --- | --- | --- |
| **Issuer** | OIDC token source trusted by Entra | Cluster's OIDC issuer URL |
| **Subject** | Specific trusted workload identity | **system:serviceaccount:orders:orders-api** |
| **Audience** | Intended token audience used for exchange | **api://AzureADTokenExchange** in standard AKS setups |

**The service account's OIDC token is not an access token for calling Azure Blob directly.** Azure Identity exchanges it for an appropriate token via Microsoft Entra; the SDK then sends that token to the Azure service.

## 10. Setting Up Microsoft Entra Workload ID on AKS

A typical workflow includes creating/attaching a user-assigned identity, enabling OIDC issuer and workload identity on AKS, creating a federated credential, declaring a Kubernetes service account, assigning data roles, and running the Pod.

The following commands are **sample operations for a lab environment**, requiring Azure/AKS administrative permissions and replacing every **<...>** placeholder. Before applying them to a cluster with existing workloads, evaluate change impact and consult docs for your exact AKS/CLI version.

### 10.1. Enabling OIDC Issuer and Workload Identity

~~~bash
az aks update   --resource-group "<aks-resource-group>"   --name "<aks-cluster-name>"   --enable-oidc-issuer   --enable-workload-identity

# Read the real OIDC issuer URL from AKS.
az aks show   --resource-group "<aks-resource-group>"   --name "<aks-cluster-name>"   --query "oidcIssuerProfile.issuerUrl"   --output tsv
~~~

For new clusters, the corresponding features can be configured at cluster creation time. Enabling them on an existing cluster is an **infrastructure configuration change**; do not apply it in production without an appropriate change process.

### 10.2. Creating a User-Assigned Identity

~~~bash
az identity create   --resource-group "<identity-resource-group>"   --name "<orders-identity-name>"

az identity show   --resource-group "<identity-resource-group>"   --name "<orders-identity-name>"   --query "{clientId:clientId, principalId:principalId, id:id}"   --output json
~~~

Save the **client ID** for the Kubernetes service account and the **principal ID** for RBAC. Do not store any secret, because a user-assigned identity requires no client secret when used in properly configured workload federation.

### 10.3. Creating a Federated Identity Credential

~~~bash
az identity federated-credential create   --resource-group "<identity-resource-group>"   --identity-name "<orders-identity-name>"   --name "orders-api-federation"   --issuer "<aks-oidc-issuer-url>"   --subject "system:serviceaccount:orders:orders-api"   --audiences "api://AzureADTokenExchange"
~~~

Here:

- **orders** is the Kubernetes namespace.
- **orders-api** is the Kubernetes service account name.
- If the namespace or service account name changes, **the federated credential's subject must be updated**.
- Issuer must be the actual URL of the cluster with OIDC issuer enabled.
- Audience must match the workload's federation configuration.

The federation record does not grant Azure data roles by itself: you still need role assignments for the identity's principal ID on resources like Blob/Service Bus/Key Vault.

### 10.4. Declaring the Kubernetes Service Account and Pod

Example service account:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "<user-assigned-identity-client-id>"
~~~

The Deployment's Pod template needs the right service account and label so the Workload ID webhook processes it:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api
      containers:
        - name: api
          image: "<container-registry>/orders-api:<image-tag>"
          ports:
            - containerPort: 8080
~~~

This YAML is a deployment skeleton illustrating the identity setup; production needs health probes, resource limits, security contexts, and proper application configuration.

When the Pod is properly processed by Workload ID, the environment may be injected with variables such as:

~~~text
AZURE_CLIENT_ID=<client-id>
AZURE_TENANT_ID=<tenant-id>
AZURE_FEDERATED_TOKEN_FILE=<path-to-projected-oidc-token>
~~~

These variables are **inputs for the Azure Identity SDK**, not places to store manual secrets. Never copy token files into a container image, and never place OIDC tokens into logs or Git.

### 10.5. Java Using WorkloadIdentityCredential

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.WorkloadIdentityCredentialBuilder;

TokenCredential credential =
        new WorkloadIdentityCredentialBuilder().build();
~~~

In an environment with the variables/token file properly set up as above, the builder can read configuration from the environment. If your SDK version requires explicit configuration or different variable names, use the API matching the deployed release.

An application can use **DefaultAzureCredential** to leverage workload identity support in a compatible Azure Identity version. However, if production requires federation exclusively, an explicit **WorkloadIdentityCredential** makes misconfiguration fail clearly.

**Pitfall to avoid:** letting a Pod use a node identity or CLI cache and concluding workload federation is working. Integration tests must prove that requests originate from the federated identity bound to the intended service account.

## 11. Workload Identity in CI/CD

Many CI systems can issue an **OIDC token** to a job. Microsoft Entra can trust an issuer/subject/audience scoped to a repository, branch, environment, or job type, depending on the CI provider.

Example implementation mindset:

1. Register an application or create a supported Entra identity for CI.
2. Configure a **federated identity credential** bound to the specific CI subject.
3. Grant the job permission to request an OIDC token via the provider's mechanism.
4. Use an Azure login step supporting federation inside the job.
5. Grant only **deploy** permissions if the job only deploys; use a separate identity/permissions for integration tests if data access is needed.
6. Verify that JVM tests actually use the configured credential source.

With GitHub Actions, a job typically needs the **id-token: write** permission to obtain an OIDC token, along with an OIDC-compatible Azure login action. Exact action/version details, subject claims, and organizational policies must be verified against current documentation before deployment.

**A common architectural mistake:** a pipeline logs in via Azure CLI successfully and then runs Java integration tests with **DefaultAzureCredential**, yet the SDK picks another environment credential source; the test runs under the wrong principal. To be certain of the identity, choose a specific credential for tests or constrain the credential source list and inspect which source is actually used.

### Deploy Identity Differs from Runtime Identity

| Identity | Required Permissions | Should Not Be Granted by Default |
| --- | --- | --- |
| **CI deployer** | Permission to update App Service/AKS resources or deploy artifacts within required scope | Permission to read all production secrets and data |
| **Spring Boot runtime** | Least-privilege data permissions on the corresponding Blob, Service Bus, Key Vault, or Cosmos | Owner permission on the subscription |
| **Integration test** | Permissions on test resources and test-data cleanup | Permissions to modify production outside test scope |

If a single pipeline needs both deployment and testing, consider using separate jobs/identities, explicit scopes, and appropriate environment gates.

## 12. Choosing an Azure Identity Credential in Spring Boot Applications

### 12.1. Decision Table

| Environment | Credential to Consider | Required Conditions |
| --- | --- | --- |
| Developer laptop | **AzureCliCredential** or controlled DefaultAzureCredential | Developer signed in, with roles on dev resources |
| App Service/VM/Functions with identity | **ManagedIdentityCredential** | Identity attached to runtime and holds roles on resource |
| AKS with Entra Workload ID | **WorkloadIdentityCredential** | Valid service account, pod label, OIDC/federation, and RBAC |
| CI with OIDC | Credential/login mechanism supported by the CI provider | Federated trust + job token + explicit role scope |
| Mixed environment using credential chain | **DefaultAzureCredential** | Sources are acceptable and the selected identity is verified |

**DefaultAzureCredential** is a convenient option when moving across environments, yet it is **not a guarantee of selecting the intended business identity**. When determinism matters, configure an explicit credential and let deployment supply the corresponding metadata.

### 12.2. Environment-Driven Credential Factory Example

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.AzureCliCredentialBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.identity.WorkloadIdentityCredentialBuilder;

public final class AzureIdentityFactory {

    private AzureIdentityFactory() {}

    public static TokenCredential create(
            String mode, String managedIdentityClientId) {

        switch (mode) {
            case "cli":
                return new AzureCliCredentialBuilder().build();

            case "managed":
                ManagedIdentityCredentialBuilder managed =
                        new ManagedIdentityCredentialBuilder();
                if (managedIdentityClientId != null &&
                        !managedIdentityClientId.isBlank()) {
                    managed.clientId(managedIdentityClientId);
                }
                return managed.build();

            case "workload":
                return new WorkloadIdentityCredentialBuilder().build();

            case "default":
                return new DefaultAzureCredentialBuilder().build();

            default:
                throw new IllegalArgumentException(
                        "Unknown Azure identity mode: " + mode);
        }
    }
}
~~~

This is an illustrative factory; in a Spring Boot application, you can expose the result as a **@Bean TokenCredential** and inject it into SDK clients. These modes must be determined by a trusted deployment/configuration layer; never allow API callers to choose an identity arbitrarily.

### 12.3. Wiring into the Azure SDK

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

TokenCredential credential =
        AzureIdentityFactory.create("managed", System.getenv("AZURE_CLIENT_ID"));

BlobServiceClient blobServiceClient = new BlobServiceClientBuilder()
        .endpoint("https://<account-name>.blob.core.windows.net")
        .credential(credential)
        .buildClient();
~~~

Only use this pattern when running in an **environment that provides a managed identity**. For a local developer, choose **cli** mode; for AKS Workload ID, choose **workload** once OIDC and projected tokens are properly configured.

In a Spring Cloud Azure starter setup, you can rely on auto-configuration to build the client; when you need custom beans, manage bean conflicts and credential properties per your Spring Cloud Azure version.

## 13. Testing: Proving the Right Identity and Permissions

A good test suite must distinguish **build succeeded**, **client instantiated**, **token acquired**, and **data operation genuinely succeeded**.

### 13.1. Unit Tests

- Mock the adapter around the Azure SDK or client as fits your architecture.
- Test business behavior on upload success, timeouts, conflicts, and permission errors.
- Never use Azure CLI caches or production credentials in unit tests.
- No live Azure service calls are needed to prove business logic handling.

### 13.2. Local Integration Tests

- Use dev Azure resources and a dev identity granted explicit roles.
- If using **Azurite** for Blob, explicitly note that the emulator does not verify real Microsoft Entra managed identity, OIDC federation, or Azure RBAC.
- Verify the selected endpoint and operations on a test container, without touching real data outside test scope.

### 13.3. Cloud Integration Tests

For App Service or AKS:

1. Run using the intended runtime identity, not a developer account.
2. Verify the identity/credential source via authorized diagnostics.
3. Perform a small operation on a test resource, e.g., uploading a uniquely named blob.
4. Exercise a missing-permission case on a test resource to verify authorization error handling.
5. Delete test data and capture request/correlation IDs for troubleshooting.

**Do not stop at testing whether the Spring context starts.** Many Azure clients are constructed without contacting the service; credential/RBAC errors may appear only on the first request.

## 14. Layered Troubleshooting

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| Local **az login** succeeds, app cannot acquire token | Azure CLI is not the source the SDK chose, or the process lacks a matching CLI/session | Credential chain, runtime environment, Azure Identity diagnostics |
| **az login --identity** fails on laptop | Laptop is not running inside a managed-identity-enabled Azure host | Use user login locally; only use --identity in supported runtimes |
| App Service throws **CredentialUnavailableException** | Identity not enabled or SDK cannot detect managed identity endpoint | App Service identity, runtime configuration, SDK version |
| Wrong user-assigned identity selected | Confusing client ID with principal ID or attaching wrong identity | Client ID when creating credential, principal ID when granting RBAC |
| AKS Pod lacks federation token file | Missing Pod label, service-account annotation, or Workload ID wiring | Pod spec, service account, webhook, token projection |
| OIDC exchange rejected | Issuer/subject/audience or client/tenant mismatch | Federated credential in Entra and token metadata |
| SDK acquires token yet Blob returns **403** | Principal lacks role, wrong scope, or storage network policy | Data-plane role, target resource, firewall/Private Endpoint |
| Service Bus sender reports unauthorized | Missing **Azure Service Bus Data Sender** role, wrong namespace/entity | Namespace endpoint, principal, and sender role |
| Key Vault reports 403 | Vault permission model, missing secret permission, wrong principal | Key Vault RBAC/access policy per vault configuration |
| Timeout calling Azure | DNS, proxy, outbound routing, or Private Endpoint | Reachability from the workload itself, not just from a dev laptop |
| Role granted but not effective immediately | Propagation delay or stale token/role state | Scope, principal, elapsed time, controlled retry |

### Ordered Debugging Workflow

~~~mermaid
flowchart TD
    A[Azure request fails] --> B{Right endpoint?}
    B -->|No| C[Fix URL / account / namespace]
    B -->|Yes| D{Token acquired?}
    D -->|No| E[Check credential source and identity setup]
    D -->|Yes| F{Right principal?}
    F -->|No| G[Select identity explicitly]
    F -->|Yes| H{Sufficient permissions / network?}
    H -->|No| I[Check RBAC, scope, DNS, firewall]
    H -->|Yes| J[Check retries, throttling, service errors]
~~~

Distinguish **credential chain**, **authentication**, **authorization**, and **network** errors. Do not randomly change SDK versions when the error clearly stems from role assignments or Private Endpoint configuration.

### Safe Logging

To inspect which SDK credential source is used, enable **azure-identity** diagnostic logging per your version and within allowed scope. You may log:

- Operation name, endpoint hostname, error code, and request/correlation ID.
- Which credential type is being attempted or selected.
- Minimal masked identifiers according to internal policy.

**Never log access tokens, OIDC token files, client secrets, certificate private keys, connection strings, SAS URLs, or full environment variable dumps.** Avoid printing raw JWT payloads to logs just to inspect the principal; use authorized diagnostic tools and keep only necessary fields.

## 15. Security and Operations

1. **Least privilege:** assign data-plane roles at the narrowest scope that satisfies the application's needs.
2. **Identity separation:** dev, CI deployer, integration tests, and production runtime should use separate principals where appropriate.
3. **Avoid long-lived secrets:** prefer managed identity or federation; if client secrets/certificates are unavoidable, manage them in a secret vault and rotate per policy.
4. **Constrain OIDC trust:** strictly scope issuer, subject, audience, repo/branch/environment; never open trust to all workflows.
5. **Identity lifecycle management:** review stale role assignments when replacing workloads, deleting identities, or changing environments.
6. **Avoid unintended fallback:** production environments requiring a deterministic principal should use an explicit credential or restrict the chain.
7. **Verify both data and network layers:** even a valid role fails if private DNS or firewall rules block traffic.
8. **Regular audits:** monitor role assignments, access logs, and active identities on critical resources.

## 16. Connecting to AWS and Google Cloud

| Need | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Developer CLI | Azure CLI **az login** | AWS CLI/profile/SSO | gcloud CLI |
| Credential discovery in Java | Azure Identity **DefaultAzureCredential** | AWS SDK v2 **DefaultCredentialsProvider** | Application Default Credentials |
| Cloud workload identity | System/user-assigned managed identity | IAM role with temporary credentials | Service account / workload identity |
| Kubernetes workload federation | Microsoft Entra Workload ID for AKS | IRSA / appropriate workload identity models for EKS | Workload Identity Federation for GKE |
| CI federation | OIDC token exchanged with Microsoft Entra | OIDC → STS/AssumeRole | OIDC → Workload Identity Federation |
| Data permissions | Azure RBAC or per-service permissions | IAM/resource policies | Cloud IAM |

This is a **conceptual comparison**, not a one-to-one mapping of permissions or APIs. Each provider has its own mechanism to validate issuers, audiences, scopes, and resources. When building a multi-cloud abstraction for storage/messaging, keep **credential provider**, **resource locator**, **authorization model**, and identity **lifecycle** clearly separated.

## 17. Hands-on Exercises Across Three Environments

**Scenario:** a Spring Boot application stores documents in a private Blob container **documents** and publishes an event to Service Bus after a successful upload.

### Part A — Developer with Azure CLI

1. Sign in to the lab tenant with **az login** and verify the subscription with **az account show**.
2. Verify the storage account and endpoint with **az storage account show**.
3. Grant the required data role to the dev account on the test resource.
4. Run the application with **AzureCliCredential**, upload a Blob, and verify logs contain no tokens.
5. Revoke write permissions in the test environment, observe the failure, then restore appropriate permissions.

### Part B — App Service with Managed Identity

1. Enable system-assigned managed identity or attach a user-assigned managed identity.
2. Retrieve the exact **principal ID** and assign Blob Data Contributor and Service Bus Data Sender roles on the target resources.
3. Configure the managed identity credential, Blob endpoint, and Service Bus namespace.
4. Deploy the same business logic, test uploading and sending a message, and ensure the runtime does not depend on Azure CLI.
5. Explain why successfully deploying an application does not mean it already holds data-plane permissions.

### Part C — AKS with Workload ID

1. Enable OIDC issuer and Workload Identity if the lab cluster is permitted to be modified.
2. Create a user-assigned identity and configure a federated credential for the Kubernetes service account.
3. Set the proper annotation, Pod label, and service account in the Deployment.
4. Grant permissions to the principal ID on the Blob/Service Bus test resources.
5. Run the application with **WorkloadIdentityCredential** and verify requests succeed.
6. Intentionally alter the subject in the lab environment to observe the token-exchange failure, then restore the configuration.

**Deliverable:** a per-environment table listing **credential type**, **client/principal ID** (without secrets), **resource endpoint**, **RBAC scope**, **test outcome**, **diagnostic source**, and **rollback plan**.

### Self-Check Questions

1. Why does being signed in with Azure CLI not prove an App Service is authenticated?
2. What is the lifecycle difference between system-assigned and user-assigned managed identities?
3. When do you need the client ID and when do you need the principal ID?
4. Why must data-plane roles still be assigned even after an identity acquires a token?
5. Which three attributes must match between an AKS service account token and a federated credential?
6. Why can CI use OIDC yet a Java process still authenticate as the wrong principal?
7. What does an integration test with Azurite prove, and what does it fail to prove?
8. How should a 403 error be analyzed differently from a CredentialUnavailableException?

## 18. Key Takeaways

- **Azure CLI** serves administrative and development tasks; **managed identity** serves workloads on Azure; **workload identity federation** lets workloads like AKS/CI exchange OIDC tokens for Azure access tokens without long-lived client secrets.
- Every environment must define the **actual principal**, **credential source**, **resource endpoint**, **role/scope**, and **network**. Holding a valid token is not enough to access data.
- In Spring Boot, you can use a **Spring Cloud Azure starter** to auto-configure clients, or use **Azure SDK + TokenCredential** directly when you need control over identity selection.
- In production, prefer managed/workload identity and reduce credential-chain ambiguity with explicit configuration when needed.
- Test against real test resources, protect tokens/secrets, and clearly separate authentication, authorization, endpoint, and network-infrastructure errors.

## References

- [Authenticate to Azure using Azure CLI](https://learn.microsoft.com/cli/azure/authenticate-azure-cli)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Assign Azure roles using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)
- [Microsoft Entra Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Deploy and configure workload identity on AKS](https://learn.microsoft.com/azure/aks/workload-identity-deploy-cluster)
- [Azure Identity SDK authentication for Java](https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview)
- [Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)

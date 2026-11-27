# Distinguishing Resource Management Permissions and Data Access Permissions with Azure RBAC

A Spring Boot application may be able to create an Azure Storage Account yet receive a **403** error when uploading a Blob. Conversely, a service with only Blob write permissions can upload data successfully yet cannot update the Storage Account configuration. These two cases are not contradictory: **resource management permissions** and **data access permissions** serve different sets of operations.

In the **Azure Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, learners integrate Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries. This lesson dives into Azure RBAC, how to determine permissions when accessing storage, messaging, databases, and secrets, and how to test identity and authorization in Java applications.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish the **management plane** and **data plane** by operation type, endpoint, and authorization mechanism.
2. Read a **role definition** with **Actions**, **NotActions**, **DataActions**, and **NotDataActions**, and understand the scope and limits of each field.
3. Explain **role assignment = principal + role + scope**, permission inheritance, and the principle of least privilege.
4. Identify appropriate roles for Blob Storage, Service Bus, Event Hubs, Key Vault, App Configuration, and the dedicated mechanism for Cosmos DB.
5. Grant and verify managed identity permissions for a Spring Boot service using Azure CLI in a lab environment.
6. Diagnose cases where **sign-in succeeds but data access is denied**, separating RBAC issues from wrong endpoints, tokens, and network errors.
7. Design positive/negative tests and compare Azure authorization with AWS IAM and Google Cloud IAM.

## 2. What Are the Management Plane and Data Plane?

The **management plane** is the plane for managing Azure resources, typically going through **Azure Resource Manager (ARM)** to create, configure, list, or delete resources. The **data plane** is the plane for working with the data or business capabilities provided by that service.

| Scenario | Management Plane | Data Plane |
| --- | --- | --- |
| Azure Blob Storage | Create Storage Account, configure replication or network rules | Upload, download, list, and delete Blobs |
| Azure Service Bus | Create namespace, queue, topic, and configure entities | Send or receive messages |
| Azure Key Vault | Create vault, configure network/permission model | Read or update secret values |
| Azure Event Hubs | Create namespace, event hub, and configure infrastructure | Publish and consume events |
| Azure Cosmos DB | Create account, database/container via corresponding management API | Read, write, and query documents via data API |
| Azure App Configuration | Create store and configure resource | Read/write key-values or feature flags |

### Two Paths from a Spring Boot Application

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B{What does the app need to do?}
    B -->|Create or manage resources| C[ARM / Management SDK]
    B -->|Operate on data| D[Service Data SDK]
    C --> E[management.azure.com]
    D --> F[Blob / Service Bus / Key Vault endpoint]
    E --> G[Management-plane permissions]
    F --> H[Data-plane permissions or service access model]
    I[Microsoft Entra principal and TokenCredential] --> C
    I --> D
~~~

For example, an ARM call sent to **https://management.azure.com** uses a resource ID containing the subscription and resource group. Meanwhile, **BlobServiceClient** sends requests to an endpoint like **https://{account}.blob.core.windows.net** to upload data. They may share the same Microsoft Entra principal yet require **permissions corresponding to each operation**.

Not every service separates the two planes in the exact same way. Some container or data administration operations may exist in both management-plane and data-plane APIs. When verifying permissions, rely on the **actual operation and authorization mechanism** of the API being invoked.

## 3. What Problem Does Azure RBAC Solve?

**Azure role-based access control (Azure RBAC)** allows assigning a role defining a set of permissions to a principal within a specific scope.

~~~text
Role assignment
    = Security principal
    + Role definition
    + Scope
    + (applicable conditions, if any and supported)
~~~

Three core components:

| Component | Example | What to Check |
| --- | --- | --- |
| **Principal** | User, group, service principal, or managed identity | Actual **object/principal ID** in the tenant |
| **Role definition** | Reader, Contributor, Storage Blob Data Contributor | Which Actions/DataActions the role allows |
| **Scope** | Subscription, resource group, storage account, or supported child scope | Whether the role covers the **target resource** |

A Spring Boot application running on App Service has a **system-assigned managed identity** managed by Azure. If that identity is assigned the **Storage Blob Data Contributor** role on storage account **stordersprod01**, it can perform Blob operations permitted by that role within the matching scope. The identity of the person deploying the app does not automatically become the application's identity.

### Role Assignment Does Not Equal Authentication

First, the application needs a **valid credential** to acquire an access token. The token identifies the principal, and the service/ARM evaluates that principal's permissions on the resource scope. If you grant a role to principal A while the runtime actually uses principal B, B will still be denied.

**Azure subscription ID**, **client ID**, and **principal ID** have distinct meanings. Use **principal ID** when identifying the target receiving permissions; use **client ID** when the SDK needs to select a user-assigned managed identity; use **subscription ID** when managing ARM scopes.

## 4. Reading a Role Definition: Actions vs. DataActions

An Azure role definition typically describes permissions using the following fields:

| Property | General Meaning | Example Operations |
| --- | --- | --- |
| **Actions** | Permitted **management-plane** operations | Reading storage account configuration, creating/updating resources |
| **NotActions** | Excludes specific management operations from **that role itself** | Disallowing specific management operations listed in the role |
| **DataActions** | Permitted **data-plane** operations under the service's Azure RBAC model | Reading or writing Blobs |
| **NotDataActions** | Excludes specific data operations from **that role itself** | Excluding a specific type of data operation |
| **AssignableScopes** | Scopes where role assignments may be created for this role definition | Subscription, resource group, or supported scopes |

**NotActions/NotDataActions are not an absolute deny rule.** If a principal receives multiple role assignments, another role may grant an operation excluded by the first role. To determine effective permissions, evaluate all relevant assignments and scopes alongside role assignment conditions, deny assignments, and applicable service/infrastructure controls.

### Why Might Contributor Not Be Allowed to Write Blobs via a Microsoft Entra Token?

The **Contributor** role primarily grants the ability to manage Azure resources and typically does not include **Blob write DataActions**. A principal holding Contributor on a Storage Account may be allowed to modify resource settings, yet data-plane requests using a Microsoft Entra token will still be rejected if a data role is missing.

Similarly:

- **Reader** can view ARM resource configuration metadata, but that does not grant permission to read private Blob contents or secrets.
- **Storage Blob Data Reader** grants Blob data read permissions matching the scope; it does not allow editing the Storage Account's network/firewall configuration.
- **Storage Blob Data Contributor** grants the data permissions needed to read/write/delete Blobs per the role; it does not grant permission to create a new Storage Account.
- **Owner** can manage access permissions at the granted scope, but you should not assume every data-plane token call automatically receives the corresponding **DataActions**.

### Security Exception to Understand: Indirect Data Access from the Management Plane

Some resource management roles may be permitted to perform operations such as **listKeys** on services that support access keys. If the resource permits Shared Key authentication, retrieving a key can create an **indirect data-access path** even when the role lacks direct DataActions.

For Azure Storage, for instance, carefully evaluate who has permission to retrieve account keys, whether **Shared Key authorization** should be disabled per service architecture, and which applications still rely on keys. Thus, **"Contributor does not grant Blob DataActions" does not mean management roles are always harmless to data**.

Good security practice is to use Microsoft Entra tokens, least-privilege data roles, and restricted key/secret retrieval permissions—rather than treating access keys as a shortcut around 403 errors.

## 5. Scope and Inheritance of Role Assignments

Azure RBAC has a management scope hierarchy:

~~~text
Management group
└── Subscription
    └── Resource group
        └── Resource
            └── Service-supported child scope (if applicable)
~~~

When a role is assigned at a parent scope, child resources within the inheritance path typically receive the corresponding permissions. Assigning at a smaller scope covers only that portion; for example, a Blob write role can be scoped to a storage account or a Blob container when the platform and operation support that scope.

| Example Scope | Typical Impact | Assessment for a Blob-Writing App |
| --- | --- | --- |
| Entire subscription | Can cover many current and future resources | Too broad for most applications |
| Resource group | Covers child resources within the RG | Only appropriate with clear justification |
| Storage account | Covers Blob data in the account per the role | Often a reasonable starting point |
| Blob container | Restricts data-plane scope to a supported container | Better if the application only uses one container |

**Do not conflate scope with networking.** Being in the same resource group does not mean being in the same VNet/region. An App Service in subscription A can access a Storage Account in subscription B if the identity has permissions on the target account, networking allows it, and tenant/trust settings align.

### How Effective Permissions Are Evaluated

Conceptually, consider:

1. The actual principal in use and relevant group memberships.
2. Direct role assignments and inherited assignments from parent scopes.
3. Role definitions: Actions, DataActions, and exclusions.
4. **Role assignment conditions** (if any), such as Azure ABAC conditions for Blob Storage.
5. **Deny assignments**, organizational activation states such as PIM, and other policies.
6. The service's own authorization mechanism along with network/endpoint restrictions.

Azure Policy, locks, firewalls, and other governance mechanisms can restrict operations, but **should not be viewed as replacements for role authorization**. For example, resource locks primarily affect management operations and are not a universal tool for protecting all data-plane actions.

## 6. Built-In Roles Worth Recognizing

Roles should be selected by **business capability**, not by team name. The table below illustrates common roles; exact permissions can vary by role definition version and service permission model.

| Service / Need | Commonly Suitable Role | What to Keep in Mind |
| --- | --- | --- |
| View ARM resources | **Reader** | Mainly reads metadata/management info; not data read permission |
| Routine resource management | **Contributor** | Does not grant permission to create role assignments; review sensitive management actions |
| Manage role assignments | **Role Based Access Control Administrator**, **User Access Administrator**, or appropriate role | Not needed by default for runtime applications |
| Read private Blobs | **Storage Blob Data Reader** | Choose the appropriate account/container scope |
| Read/write/delete Blobs as needed | **Storage Blob Data Contributor** | Do not use as a substitute for ARM permissions |
| Send Service Bus messages | **Azure Service Bus Data Sender** | May require appropriate namespace/entity scope |
| Receive Service Bus messages | **Azure Service Bus Data Receiver** | Consumers typically need retry/idempotency design |
| Publish events to Event Hubs | **Azure Event Hubs Data Sender** | Distinct from namespace management roles |
| Consume events from Event Hubs | **Azure Event Hubs Data Receiver** | Check checkpoint store permissions if used |
| Read secret values from an RBAC-mode Key Vault | **Key Vault Secrets User** | Distinct from vault management and Keys/Certificates |
| Read key-values from App Configuration | **App Configuration Data Reader** | Does not automatically include access to secrets inside Key Vault |

**Never grant subscription-level Owner/Contributor to a production application** if it only needs to read a secret or send a few messages. Access-management roles should be restricted to authorized operations teams/automation.

### Key Vault Has Two Permission Models to Distinguish

Azure Key Vault can use:

- **Azure role-based access control permission model:** assign corresponding data-plane roles such as **Key Vault Secrets User** to read secrets.
- **Vault access policy permission model:** vault access policies define permissions for keys, secrets, or certificates under that model.

Before diagnosing a 403, check **the current vault's permission model**. Adding the Secrets User role is not guaranteed to work as expected if the vault uses the access policy model; conversely, configuring an access policy does not apply when the Azure RBAC model is enabled.

**Key Vault Contributor** manages the vault resource itself and management-plane properties; do not treat it as a role for reading all secret values. Beyond RBAC, network rules/private endpoints and secret state can still block operations.

### Cosmos DB Requires Careful Reading of Its Own Data-Plane Mechanism

**Azure Cosmos DB for NoSQL** has a **data-plane RBAC** model with its own role definitions/assignments, such as **Cosmos DB Built-in Data Reader** and **Cosmos DB Built-in Data Contributor**. This is not a case where you mechanically run standard ARM **az role assignment create** commands.

Depending on the API and service version, data-plane permissions may use Cosmos DB native role assignments, keys, or other mechanisms. For example, Cosmos DB for NoSQL provides the **az cosmosdb sql role assignment** and **az cosmosdb sql role definition** command groups to manage data permissions. Before granting access, confirm the exact Cosmos DB API, Java library in use, and account authorization model.

## 7. Complete Example: Spring Boot Writing Blobs Using Managed Identity

**Scenario:** a Spring Boot Documents API runs on Azure App Service and stores content in the **documents** Blob container of storage account **stordersprod01**. The infrastructure team is allowed to create and manage resources; the application only needs to write/read Blobs.

### 7.1. Responsibility Boundaries

| Component | Permission / Input | Typically Managed By |
| --- | --- | --- |
| Azure subscription and resource group | ARM permissions to deploy infrastructure | Platform/IaC pipeline |
| Storage account and container | Provisioned resources with appropriate network rules | Platform/data team |
| App Service managed identity | Application principal | Platform/IAM |
| Data role on Storage account/container | **Storage Blob Data Contributor** at required scope | IAM managing role assignments |
| Spring Boot Blob client | Blob endpoint, TokenCredential, container name | Application team |
| API callers | Business upload/download permissions inside the service | Spring Security / application |

An HTTP user authorized to call the Documents API endpoint **does not automatically become an Azure principal**. The backend must enforce user permissions at the application layer; the managed identity calls Blob Storage on the backend's behalf using the permissions granted to the backend.

### 7.2. Path Diagram

~~~mermaid
sequenceDiagram
    participant U as API Caller
    participant A as Spring Boot Documents API
    participant I as Managed identity / Entra
    participant B as Azure Blob Storage
    U->>A: POST document
    A->>A: Check business authorization
    A->>I: Request access token for Storage
    I-->>A: Managed identity token
    A->>B: Upload Blob + token
    B->>B: Check data-plane permissions / network
    B-->>A: Success or 401/403/other error
    A-->>U: Business result
~~~

**The management permissions of the person deploying App Service do not automatically "pass down" to the Java process's managed identity.** You must assign the data role directly to the exact principal or a group containing that principal at the appropriate scope.

### 7.3. Spring Cloud Azure Starter Configuration

With a **Spring Cloud Azure** version matching Spring Boot, add the Blob starter:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
~~~

This POM is a **snippet**. The project must manage versions through the **com.azure.spring:spring-cloud-azure-dependencies** BOM compatible with its Spring Boot line, rather than pinning arbitrary version numbers on the starter.

Configuration in **application.yml**:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}

app:
  blob:
    container: ${AZURE_BLOB_CONTAINER:documents}
~~~

For example, set **AZURE_STORAGE_ACCOUNT=stordersprod01** in the deployment environment. Azure Identity will use the credential source configured according to the chosen Spring Cloud Azure/SDK mechanism. In production with managed identity, verify that the **right identity is actually used**; if the runtime has multiple credential sources, configure or inject the credential explicitly per your version's documentation.

### 7.4. Java Service Using BlobServiceClient

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentsStorage {

    private final BlobContainerClient container;

    public DocumentsStorage(
            BlobServiceClient blobServiceClient,
            @Value("${app.blob.container}") String containerName) {
        this.container = blobServiceClient.getBlobContainerClient(containerName);
    }

    public void upload(String blobName, byte[] bytes) {
        container.getBlobClient(blobName).upload(
                new ByteArrayInputStream(bytes),
                bytes.length,
                false
        );
    }
}
~~~

The **upload** method uses **overwrite=false** to avoid silently overwriting data. This is a data-access example; the code does not create the storage account, assign roles, or auto-create the container. In a real application, enforce file size limits, validate API user permissions, sanitize Blob names, handle streaming, retries, and conflict handling appropriately.

**Successfully instantiating BlobServiceClient does not prove the required DataActions exist**. You must run an actual request; many SDK clients defer authentication and connection setup until first use.

### 7.5. If Using the SDK Directly

When not using the starter, you still use an Azure Identity credential and the Azure Storage SDK:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

TokenCredential identity =
        new ManagedIdentityCredentialBuilder().build();

BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint("https://stordersprod01.blob.core.windows.net")
        .credential(identity)
        .buildClient();
~~~

This example only succeeds when the environment **supports managed identity**, the identity is properly enabled/attached, and it holds the appropriate data-plane permissions. **DefaultAzureCredential** can be used in environments where the credential chain is controlled; it does not automatically pick an identity based on which role has the highest privilege.

## 8. Azure CLI Practice: Inspecting Roles and Assigning Permissions at the Right Scope

The commands below are meant for a **lab with test resources and granted administrative permissions**. Values in angle brackets are placeholders; do not run directly against a production subscription without an appropriate permission-change workflow.

### 8.1. Identifying the Right Subscription and Resource ID

~~~bash
az login

az account show   --query "{subscription:id, tenant:tenantId, name:name}"   --output json

az account set --subscription "<subscription-id>"

az storage account show   --resource-group "<resource-group>"   --name "<storage-account>"   --query "{id:id, name:name, endpoints:primaryEndpoints}"   --output json
~~~

A Storage Account resource has a typical ARM ID:

~~~text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account>
~~~

The **Resource ID** is the scope for managing and assigning permissions to the resource, whereas the Blob data endpoint has the form **https://{account}.blob.core.windows.net**. Never pass an ARM resource ID as the URL in BlobServiceClient.

### 8.2. Inspecting the Managed Identity's Principal

For an App Service with system-assigned managed identity enabled:

~~~bash
az webapp identity show   --resource-group "<app-resource-group>"   --name "<app-service>"   --query "{principalId:principalId, tenantId:tenantId, type:type}"   --output json
~~~

For a user-assigned managed identity:

~~~bash
az identity show   --resource-group "<identity-resource-group>"   --name "<identity-name>"   --query "{id:id, clientId:clientId, principalId:principalId}"   --output json
~~~

Note: **client ID** specifies the identity in certain Azure Identity credential builders; **principal ID** is the identifier needed when assigning roles to the identity.

### 8.3. Inspecting Role Definitions and Distinguishing Actions vs. DataActions

~~~bash
az role definition list   --name "Contributor"   --output json

az role definition list   --name "Storage Blob Data Contributor"   --output json
~~~

In the output, locate the **permissions** field containing **actions/notActions/dataActions/notDataActions**. You can compare management roles with data roles. Do not judge a role solely by its display label; inspect the actual role definition and assignment scope.

### 8.4. Assigning the Blob Data Contributor Role

The user running the command must have permission to create role assignments at the appropriate scope, such as an authorized access-management role:

~~~bash
az role assignment create   --assignee-object-id "<managed-identity-principal-id>"   --assignee-principal-type ServicePrincipal   --role "Storage Blob Data Contributor"   --scope "<storage-account-resource-id>"
~~~

The command assigns the role to the **exact principal ID** on the **exact storage account**. For an application accessing only a single container, consider container scope where supported and operationally practical.

There is no need to grant subscription-wide **Owner** just so a service can write Blobs. After assigning a role, it may take time for permissions to propagate across services and related tokens/caches.

### 8.5. Viewing Assigned Permissions

~~~bash
az role assignment list   --assignee "<managed-identity-principal-id>"   --scope "<storage-account-resource-id>"   --include-inherited   --output table
~~~

If the expected role does not appear, check tenant/subscription, principal ID, scope, the caller's read permissions, and inheritance. Seeing a role in the list still does not guarantee requests will succeed if the service uses a different authorization model or networking blocks access.

### 8.6. An Important Limitation of Testing via Azure CLI

You can use a developer account to test reading Blobs using a Microsoft Entra token:

~~~bash
az storage blob list   --account-name "<storage-account>"   --container-name "documents"   --auth-mode login   --output table
~~~

That command verifies permissions **of the identity currently signed in to the Azure CLI**, not necessarily the App Service's managed identity. If the CLI succeeds while the Spring Boot runtime fails, you cannot conclude the application has permissions. **Integration tests must run under the application's actual runtime identity**.

To validate the App Service managed identity's permissions, invoke a real Blob operation from the deployed application and collect the appropriate status code / request ID.

## 9. Service-Specific RBAC Roles: How to Choose Correctly

### 9.1. Blob Storage

A document storage system can separate principals:

| Principal | Business Purpose | Suitable Role |
| --- | --- | --- |
| Documents API | Upload and update Blobs | **Storage Blob Data Contributor** |
| Reporting API | Download Blobs read-only | **Storage Blob Data Reader** |
| Platform deployment | Create/configure Storage Account | Resource management permissions per IaC/scope |
| IAM operator | Create role assignments | Delegated role-assignment management permissions |

In Storage, some operations such as **listing containers** or managing metadata involve API/plane distinctions. Specific permissions must be checked per operation: do not infer them solely from "holding Reader on the Storage Account".

**Shared Key/SAS** is a separate authentication path from RBAC tokens. If an application uses a connection string containing an account key, requests may succeed without reflecting the principal's **Storage Blob Data Contributor** role. When practicing RBAC, use **--auth-mode login** or SDK **TokenCredential** to avoid testing the wrong mechanism.

### 9.2. Service Bus

Azure Service Bus separates queue/topic administration from message processing:

- Administrators can create queues/topics and configure entity properties.
- Producers only need **Azure Service Bus Data Sender** at the appropriate scope.
- Consumers only need **Azure Service Bus Data Receiver** at the appropriate scope.
- A workload that both sends and receives may combine roles per business requirements; there is no need for full-control roles.

The Spring Cloud Azure Service Bus starter helps configure clients and Spring integration, but does not create role assignments. Constructing a **ServiceBusSenderClient** does not prove the principal has permission to send messages; errors may surface only on the actual send.

### 9.3. Event Hubs

Separate creating namespaces/event hubs from publishing/consuming events. Use **Azure Event Hubs Data Sender** or **Azure Event Hubs Data Receiver** as needed.

If a consumer uses Blob Storage to store checkpoints, it may need a **separate Blob role for the checkpoint store**. Permission to read events on Event Hubs does not automatically grant permission to write checkpoint Blobs; an error appearing to come from Event Hubs may actually originate from another Storage Account.

### 9.4. Key Vault and App Configuration

A Spring Boot service reading configuration from App Configuration and fetching secrets from Key Vault involves **two resources and two sets of data permissions**:

| Resource | Need | Typical Permission |
| --- | --- | --- |
| App Configuration store | Read key-values / feature flags | **App Configuration Data Reader** |
| Key Vault | Read secret values | **Key Vault Secrets User** when using the RBAC model |
| Same resources at management plane | Create/operate resources | Corresponding management role |

Having App Configuration reference a Key Vault secret does not mean App Configuration permissions automatically grant Key Vault read access. Before granting a Key Vault role, verify whether the vault uses **Azure RBAC** or an **access policy**.

### 9.5. Cosmos DB

For Cosmos DB for NoSQL, a Spring Data Cosmos repository reading/writing items must use authorization supported by the **Cosmos DB data plane**. Under native RBAC, roles such as **Cosmos DB Built-in Data Contributor** are assigned via **Cosmos DB SQL role assignments**.

Do not use the **Contributor** role on a Cosmos DB account to assume **CosmosAsyncClient** can query or upsert items when authenticating with an Entra token. Likewise, do not assume different Cosmos DB APIs share the same role set, SDK, or authentication model.

## 10. Authentication, RBAC, and Network: Accurate Error Classification

A request to a service can fail at different layers:

~~~mermaid
flowchart TD
    A[Spring Boot calls Azure SDK] --> B{Right service endpoint?}
    B -->|No| E1[Fix account / namespace / URL]
    B -->|Yes| C{Credential acquired token?}
    C -->|No| E2[Check tenant / identity / token source]
    C -->|Yes| D{Request reached service?}
    D -->|No| E3[Check DNS / firewall / Private Endpoint]
    D -->|Yes| F{Principal permitted for operation?}
    F -->|No| E4[Check DataActions / scope / permission model]
    F -->|Yes| G[Check business logic, quota, conflict, throttling]
~~~

| Symptom | Common Causes | How to Verify |
| --- | --- | --- |
| **CredentialUnavailableException** | Runtime has no supported credential source | Check managed/workload identity, environment variables, and credential chain |
| **AuthenticationFailedException** | Invalid tenant, issuer, federated trust, or credential | Identify actual identity, token source, and Entra configuration |
| Client has token yet Blob upload returns **403** | Missing Blob write DataActions, scope does not cover resource, or policy/network | Check Storage Blob Data Contributor and Azure Storage error code |
| Azure CLI reads ARM resource yet listing Blobs fails | Principal holds management role but lacks data-plane permission | Compare Contributor/Reader against Blob Data Reader |
| Key Vault returns **403** | Missing secret permission or vault permission model differs from expectation | Check vault RBAC/access policy, role, and scope |
| Service Bus message send rejected | Principal lacks Data Sender role or wrong namespace | Verify target entity and data role |
| SDK timeout | DNS, private endpoint, outbound route, or firewall | Check connectivity from the App Service/Pod/VM itself |
| **401** when calling service | Invalid token, wrong audience/authority, or expired | Verify endpoint, SDK, and token source |
| **404/409/429** | Wrong resource name, conflict, quota, or throttling | Read the specific error code; do not jump to blaming missing RBAC |

**Do not assume 403 always means a missing role.** Some services return 403 for network policies, and other systems return service-specific error codes. Inspect the **service error code**, request ID, principal, and endpoint to pinpoint the cause.

### Impact of Role Propagation and Token Caching

A newly created role assignment may not take effect immediately due to permission propagation and caching. Do not work around it by granting broader roles. Verify the exact assignment/scope, wait per service guidance, and re-run a controlled request. Token and SDK/runtime caching mechanisms can also vary when updates take effect.

If the organization uses **Privileged Identity Management (PIM)** or eligible assignments, verify whether the role is **active**; an eligible role may require activation before use.

## 11. Designing Permission Tests Under Least Privilege

Running only unit tests that verify Spring context startup is insufficient. To verify RBAC, you must run an actual test calling the service using the **intended identity**.

### 11.1. Unit Tests

- Mock or stub the adapter around the Azure SDK to verify business handling when requests return success/403/404/409.
- Verify the application's API prevents users without business permissions from invoking write/delete operations.
- Do not make unit tests depend on Azure CLI login, client secrets, or a developer's subscription.

### 11.2. Integration Tests in an Azure Lab Environment

For example, prepare three separate identities on a test storage account:

| Test Identity | Role | Expected Outcome |
| --- | --- | --- |
| **reader-test** | Storage Blob Data Reader | Reading blobs succeeds; writing blobs is denied |
| **writer-test** | Storage Blob Data Contributor | Reading/writing blobs succeeds within granted scope |
| **management-test** | Management-plane Reader, no data role | Can view resource metadata if permitted, yet cannot read private Blobs via Entra token |

For identities carrying stronger management permissions, watch out for the **indirect key-access path** noted in Section 4. For tests to genuinely evaluate RBAC tokens, do not use a connection string containing an account key.

"Must-be-denied" tests should be executed on **lab resources**, never by revoking permissions on production applications or altering shared team roles.

### 11.3. Limitations of Emulator Testing

**Azurite** is useful for testing many Blob/Queue operations during development, but it is not a full equivalent of Microsoft Entra, Azure RBAC, deny assignments, PIM, or real Azure private networking. It does not prove the runtime principal has the right permissions on a production storage account.

**An application can start in Spring Boot without having validated RBAC:** many Azure SDK clients only acquire tokens and contact endpoints on the first actual request.

### 11.4. Logging and Investigation Readiness

Collect in a controlled manner:

- **Operation** and resource/endpoint hostname.
- HTTP/gRPC/AMQP error code or service-specific error code.
- **Azure request ID/correlation ID**, timestamp, retry count, and latency.
- Credential/identity type in use at a metadata level approved for internal logging.
- Relevant scope and role assignments during an authorized investigation.

**Never log** access tokens, refresh tokens, account keys, connection strings, SAS URLs, secret values, or workload federation token contents. Tenant/principal/resource IDs must also be handled according to internal data policies.

## 12. Analysis Scenarios: One Principal, Two Types of Permissions

**Scenario A — Platform engineer:** needs to create a Storage Account and set network rules using Bicep/Terraform; afterward, the Documents API writes files.

- The deployment identity needs appropriate **management-plane** permissions to create/configure resources.
- The Documents API identity needs **Storage Blob Data Contributor** on the appropriately scoped account/container.
- If the application does not need to create Storage Accounts, do not grant resource management permissions to the application.
- The CI deployer's permissions and the App Service managed identity's permissions can be completely separated.

**Scenario B — Service Bus consumer:** the application reads messages and writes checkpoints to Blob Storage.

- **Azure Service Bus Data Receiver** permission on the namespace/entity to read from.
- Appropriate Blob permissions on the checkpoint account/container if the consumer library uses storage for checkpoints.
- No need for subscription-wide Azure Service Bus Contributor just because the consumer processes messages.

**Scenario C — Spring Boot reading configuration and secrets:**

- **App Configuration Data Reader** on the configuration store.
- **Key Vault Secrets User** if Key Vault uses the RBAC model, or the matching access policy if the vault uses that model.
- If Key Vault permission is missing, the app may still read standard key-values yet fail when resolving Key Vault references.

### Action-Based Decision Table

| What Needs to Be Done? | Permission Type to Check First |
| --- | --- |
| Create or delete Azure resources via ARM | Management Actions |
| Create role assignments | Role-assignment management permissions at scope |
| Upload or read blobs using an Entra token | Storage DataActions |
| Send/receive Service Bus messages | Sender/Receiver data roles |
| Read Key Vault secrets | Data permissions per the vault's RBAC/access policy model |
| Query Cosmos DB for NoSQL | Cosmos DB native data-plane authorization |
| Traverse firewalls/private networks | Valid network configuration; RBAC does not replace networking |

## 13. Connecting to Multi-Cloud Integration

All clouds have mechanisms for identity, roles/policies, and resource scopes, yet details differ:

| Concept | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Workload identity | Managed Identity / Workload Identity | IAM Role / STS temporary credentials | Service Account / Workload Identity |
| Resource management | Azure Resource Manager + management Actions | Service APIs/control plane + API-scoped IAM policies | Cloud Resource Manager + service APIs / IAM |
| Data access | Azure RBAC DataActions or service-specific permission model | IAM actions/resource policies per service | IAM permissions/roles and service-level access models |
| Organizational scope | Management group, subscription, resource group, resource | Organization, account, resource | Organization, folder, project, resource |
| Object storage | Azure Blob Storage | Amazon S3 | Cloud Storage |

For example, do not mechanically map **Storage Blob Data Contributor** into a "generic role" across S3 and GCS while ignoring differences in IAM policies, ACLs, bucket scopes, object prefixes, public access, service accounts, and token mechanisms.

**Spring Cloud Azure, Spring Cloud AWS, and Spring Cloud GCP** help integrate client SDKs into Spring Boot, but do not replace designing **least-privilege permissions** for each provider. When writing a multi-cloud adapter, factor in **principal**, **permission scope**, **service endpoint**, and **failure semantics**, not just upload/download method names.

## 14. Lab Exercise: Proving the Difference Between the Two Planes

**Scenario:** create a Spring Boot Documents API accessing a private Blob container **documents** in a lab account. The goal is to observe behavior as management and data roles change.

1. **Prepare the lab:** create or obtain a Storage Account, Blob container, and two test identities; record the subscription ID, account resource ID, and Blob endpoint. Do not use production.
2. **Verify ARM:** using an identity with management-plane read permissions, inspect Storage Account metadata via Azure CLI **az storage account show**.
3. **Grant only management Reader:** use a principal without Blob Data Reader; attempt to list Blobs with **--auth-mode login** or SDK TokenCredential. Record the outcome and service error code.
4. **Grant Blob Data Reader:** at a supported account/container scope, test reading a Blob; attempt an upload and verify write access is denied.
5. **Grant Blob Data Contributor:** verify uploading a uniquely named Blob succeeds; read it back, then clean up.
6. **Test in Spring Boot:** inject BlobServiceClient from the Spring Cloud Azure starter or build the client using Azure Identity SDK; run the operation under a real managed identity rather than drawing conclusions from a developer CLI session.
7. **Extend:** add a Service Bus queue or Key Vault in test resources and verify Data Sender/Secrets User roles under that service's exact permission model.
8. **Report:** compile a table of role definitions, principal IDs, scopes, endpoints, ARM/data operations, error codes, and explanations. Revoke temporary role assignments created for the lab according to test-environment procedures.

### Self-Check Questions

1. Why can someone with the **Reader** role inspect a Storage Account yet fail to read private Blob contents via an Entra token?
2. Does the **Contributor** role automatically include all Storage **DataActions**? What indirect data-access path must be considered?
3. Why is **NotDataActions** in one role not a deny that applies across all other role assignments?
4. If the Documents API receives **403** when uploading, what details should you inspect before granting additional roles?
5. Why does a successful **az storage blob list --auth-mode login** on a developer machine not confirm the App Service managed identity's permissions?
6. Why might an Event Hubs consumer using Blob checkpoints need permissions across two different services?
7. When Key Vault uses the access policy model, what happens if you rely solely on the RBAC Secrets User role without checking the permission model?
8. Why can you not use standard ARM management roles to conclude that Cosmos DB for NoSQL permits querying documents with an Entra token?

## 15. Key Takeaways

- **Management plane** manages resources; **data plane** operates on data/services. A principal permitted on one plane is not necessarily permitted on the other.
- **Azure RBAC = principal + role definition + scope**; verify **Actions** and **DataActions**, inheritance, conditions/deny assignments, and effective permissions rather than relying on role display names alone.
- **Contributor/Reader/Owner** have different management semantics from **Storage Blob Data Reader/Contributor**; sensitive management actions such as **listKeys** can create indirect data-access paths.
- **Key Vault** requires checking RBAC vs. access policy models; **Cosmos DB for NoSQL** has its own data-plane RBAC mechanism; **Service Bus/Event Hubs** have dedicated sender/receiver roles.
- In Spring Boot, **Spring Cloud Azure starters and the Azure SDK** do not grant permissions by themselves. Verify with real requests using the **actual runtime identity**, endpoint, RBAC scope, and network path.
- Apply least privilege, separate deploy identities from runtime identities, protect secrets, and test denied scenarios on lab resources.

## References

- [What is Azure RBAC?](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Understand Azure role definitions](https://learn.microsoft.com/azure/role-based-access-control/role-definitions)
- [Understand Azure role assignments](https://learn.microsoft.com/azure/role-based-access-control/role-assignments)
- [Azure RBAC best practices](https://learn.microsoft.com/azure/role-based-access-control/best-practices)
- [Assign an Azure role using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)
- [Authorize access to blobs using Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Azure Key Vault RBAC guide](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Azure Cosmos DB for NoSQL role-based access control](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)

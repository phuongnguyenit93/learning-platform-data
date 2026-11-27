# Subscription, Resource Group, Tenant, and Service Endpoints on Azure

When integrating Spring Boot with Azure, developers frequently encounter values such as **tenant ID**, **subscription ID**, **resource group**, **resource ID**, **resource name**, and **endpoint**. They all describe parts of an Azure system, yet answer different questions. Confusing them can cause an application to call the wrong resource, acquire a token from the wrong tenant, lack data permissions, or fail to connect even with valid credentials.

This lesson belongs to the **Azure Platform** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing integrating Spring Boot with managed services across AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries. The concepts below lay the groundwork for identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish **Microsoft Entra tenant**, **Azure subscription**, **resource group**, **resource**, and **service endpoint**.
2. Read and analyze an **Azure resource ID**; understand the relationship between subscription, resource group, and resources.
3. Explain why calling an Azure SDK data plane typically requires **endpoint + credential + permissions**, while creating/managing resources also requires a **management scope**.
4. Configure a Spring Boot application using Spring Cloud Azure / Azure SDK to connect to Blob Storage with the right account and identity.
5. Diagnose errors involving wrong subscription, wrong tenant, wrong endpoint, missing RBAC, and Private Endpoint/DNS configuration.
6. Compare Azure's resource organization model with corresponding concepts in AWS and Google Cloud.

## 2. The Big Picture: What Is Each Component Responsible For?

| Concept | Question Answered | Illustrative Example | What It Is Not |
| --- | --- | --- | --- |
| **Tenant** (Microsoft Entra ID) | Which identity directory do user/workload identities belong to? | GUID-formatted Tenant ID | A Blob address or resource group |
| **Subscription** | Under which Azure unit are resources governed and billed? | GUID-formatted Subscription ID | An application login account |
| **Resource group** | Which resources are organized and managed within a shared lifecycle/scope? | `rg-orders-prod` | A private network or a uniform deployment region |
| **Resource** | Which specific Azure entity is being used? | Storage account `stordersprod01` | A Java SDK/client object |
| **Endpoint** | Which host/URL does the client send requests to? | `https://stordersprod01.blob.core.windows.net` | An Azure resource ID or authorization grant |
| **Principal and role assignment** | Who is allowed to perform what actions on which resource scope? | Managed identity with a Blob write role | Automatically inferred from a valid URL |

**A rule of thumb:** tenant and principal relate to **identity**; subscription/resource group/resource relate to **organization, governance, and permission scope**; endpoint relates to **network communication target**. These axes connect together, yet cannot be swapped for one another.

### Relationship Diagram

~~~mermaid
flowchart TD
    T["Microsoft Entra tenant A\nContains user / application identities"] --> S1["Subscription S1"]
    T --> S2["Subscription S2"]
    S1 --> RG1["Resource group rg-orders-prod"]
    S1 --> RG2["Resource group rg-network-prod"]
    S2 --> RG3["Resource group rg-data-shared"]
    RG1 --> APP["App Service or AKS workload"]
    RG3 --> ST["Storage account"]
    RG3 --> SB["Service Bus namespace"]
    APP -. "HTTPS to endpoint + token + RBAC" .-> ST
    APP -. "AMQP/HTTPS + token + RBAC" .-> SB
~~~

Arrows from the tenant to subscriptions represent a **governance/identity relationship** in the typical case—not that every resource in a subscription automatically grants access to every principal in the tenant. Dashed arrows represent **data-plane connections**: an application can access resources in a **different subscription** when identity, permission, and network requirements are satisfied.

## 3. Tenant: The Identity Boundary of Microsoft Entra ID

**Microsoft Entra ID** (formerly Azure Active Directory) is the identity and access management system. A **tenant** is an organization's Entra directory instance/unit. A tenant contains entities such as users, groups, registered applications, and service principals; a managed identity also has a principal representation in the identity system.

Common identifiers:

| Name | Meaning | Where It Is Used |
| --- | --- | --- |
| **Tenant ID** / directory ID | Entra directory identifier, typically a GUID | Identifying the token-issuing organization or configuring the authority |
| **Application (client) ID** | Identifier of a registered application or client identity | Selecting the corresponding app/managed identity in authentication flows |
| **Object ID / principal ID** | Identifier of a specific object within a tenant | Role assignments and principal lookups |
| **Subscription ID** | Azure Resource Manager subscription identifier | Resource management, scoped authorization, billing |

**Client ID differs from object/principal ID**. For a user-assigned managed identity, the client ID can be used to select the identity when acquiring a token, whereas the principal ID is typically used to specify the target receiving a role assignment. Do not copy the wrong value when configuring.

### One Tenant Can Have Multiple Subscriptions

For example, an organization has tenant `tenant-company` and two subscriptions `sub-dev` and `sub-prod`. A user signs in to the same tenant but can only see resources in `sub-dev` if their role assignments do not cover `sub-prod`. **Signing in to a tenant does not imply permission to access all subscriptions under that tenant**.

An Azure subscription is typically associated with **one Microsoft Entra directory at a time**. Cross-organization access scenarios may use B2B guests, multi-tenant applications, or an appropriate delegation model; do not assume a managed identity in tenant A automatically has permissions in tenant B.

### Authentication and Authorization Are Two Separate Steps

- **Authentication:** Entra or an appropriate credential source identifies the caller and issues a token for the intended service/audience.
- **Authorization:** the Azure service checks whether the principal has permission for the operation and target resource; depending on the service, this may be Azure RBAC, service-specific data-plane RBAC, or a policy/access control mechanism.
- **Network admission:** firewalls, private endpoints, network rules, and DNS can still block connections even when the token and role are valid.

For example: an application successfully acquires a token from a managed identity, yet uploading to Blob Storage fails with **403**. The cause could be a missing **Storage Blob Data Contributor** role at the right scope; you also need to check network policies and the service's detailed error response. Randomly changing the tenant ID will not solve missing data permissions.

## 4. Subscription: The Unit of Governance, Quotas, and Billing

An **Azure subscription** is a scope for managing resources through Azure Resource Manager (ARM). Each subscription has a **subscription ID**; inside it live resource groups and resources. Concerns typically tied to a subscription include:

- **Billing and cost tracking:** resource charges are recorded under the associated billing account/subscription structure.
- **Governance:** Azure Policy, resource locks, role assignments, and certain limits/quotas.
- **Resource deployment:** ARM operates on resource IDs containing the subscription ID; IaC must select the target subscription.
- **Environments:** organizations often separate dev/test/prod or product groups into separate subscriptions for more independent governance.

A subscription **is not** a DNS namespace for every service. Two storage accounts can sit in two different subscriptions yet share the Azure Blob DNS suffix; the storage account's own name and endpoint determine the data connection target.

### Management Groups and Scope Hierarchy

An organization can manage multiple subscriptions using **Azure management groups**. Roles, policies, and governance controls can be applied or inherited down the hierarchy:

~~~text
Tenant / organization
└── Management group(s) (if configured)
    └── Subscription
        └── Resource group
            └── Resource
~~~

A **role assignment scope** is typically chosen at the management group, subscription, resource group, or resource level, depending on the permissions and service type. Assigning a role at a broad scope can grant permissions across many child resources; the **least privilege** principle favors the smallest scope that meets the requirement. Do not view a subscription as a "network" or a "geographic region": resources in the same subscription can span multiple regions and multiple networks.

### When Does an Application Need the Subscription ID?

- When using the **Azure Resource Manager SDK/REST** to create, list, update, or delete Azure resources by subscription/resource group.
- When deploying ARM/Bicep/Terraform or automating administrative operations.
- When specifying RBAC scopes, Azure Policy, resource IDs, and billing information.

Conversely, for most **Blob data-plane** calls such as uploading a blob with `BlobClient`, the SDK needs the account endpoint, a credential, and appropriate write permissions. **The subscription ID does not necessarily appear in the upload code**. An identity can still access an account in another subscription if permissions and networking allow it.

## 5. Resource Group: The Unit of Organization and Resource Lifecycle

A **resource group (RG)** is a logical container belonging to **one subscription**. Each standard ARM resource belongs to one resource group at a time; a single resource group can hold resources of different types and across different regions.

A resource group helps with:

1. **Application/system-scoped deployments** using ARM, Bicep, Terraform, or pipelines.
2. **Authorization** at the RG scope when multiple resources share the same operators.
3. **Applying policies, locks, and tags** for governance according to the model chosen by the organization.
4. **Lifecycle management:** deleting an RG can delete the resources inside it, requiring strict change control.

Example:

| Subscription | Resource group | Resource | Purpose |
| --- | --- | --- | --- |
| `sub-app-prod` | `rg-orders-app-prod` | App Service or AKS | Runs Spring Boot services |
| `sub-data-prod` | `rg-orders-data-prod` | Storage account, Service Bus | Stores files and processes messages |
| `sub-network-prod` | `rg-shared-network-prod` | VNet, private DNS zone, Private Endpoint | Shared networking by design |

This is an **illustrative** organization, not a mandatory rule. An RG name by itself does not create network connectivity or access permissions; the application still needs an endpoint, credentials, RBAC, and actual network connectivity.

### A Resource Group Also Has a Location, with a Different Meaning

When creating an RG, Azure requires a **location for the resource group's metadata**. This location does not force every resource inside the RG to be deployed in the same region. Each resource has its own location and deployment capabilities; some resources are global or use a different region/replication model.

For example: an RG whose metadata is in Southeast Asia can still contain a storage account in East Asia if service rules and policies allow it. Therefore, do not infer an Azure service endpoint or data residency solely from the RG's location.

## 6. How Resource ID, Resource Name, and Endpoint Differ

Suppose we have:

- Tenant `11111111-1111-1111-1111-111111111111` (example ID).
- Subscription `22222222-2222-2222-2222-222222222222` (example ID).
- Resource group `rg-orders-data-prod`.
- Storage account `stordersprod01`.

The **Azure resource ID** of the storage account has the ARM structure:

~~~text
/subscriptions/22222222-2222-2222-2222-222222222222
/resourceGroups/rg-orders-data-prod
/providers/Microsoft.Storage/storageAccounts/stordersprod01
~~~

This is **a single resource ID**; the example is wrapped across lines for readability. In API or CLI configurations, the segments must be joined on one line:

~~~text
/subscriptions/22222222-2222-2222-2222-222222222222/resourceGroups/rg-orders-data-prod/providers/Microsoft.Storage/storageAccounts/stordersprod01
~~~

Meanwhile, the Blob Storage **data endpoint** is typically:

~~~text
https://stordersprod01.blob.core.windows.net
~~~

| Component | Shape | Used For |
| --- | --- | --- |
| **Resource ID (ARM)** | `/subscriptions/.../resourceGroups/.../providers/...` | Uniquely identifying a resource in Azure Resource Manager, IAM, deployments |
| **Resource name** | `stordersprod01` | Naming the resource; for some services, used in DNS |
| **Service/data endpoint** | `https://stordersprod01.blob.core.windows.net` | Sending Blob data requests from Azure SDK/HTTP |
| **Management endpoint** | `https://management.azure.com` (Azure public cloud) | Calling ARM REST APIs to create/update/list resources |
| **Identity authority** | e.g., `https://login.microsoftonline.com/{tenantId}` | Acquiring tokens per tenant and supported authentication flow |

**Do not** pass an ARM resource ID into the endpoint parameter of `BlobServiceClientBuilder`. Similarly, do not use a Blob endpoint as a subscription ID. If you need to manage the storage account, use Azure Resource Manager / ARM SDK with subscription, resource group, and resource ID; if you need to upload blobs, use the Azure Storage Blob SDK with the data endpoint.

### Uniqueness Scope of Resource Names

Naming rules **vary by service**: some names must be globally unique in DNS (such as storage account names in Azure public cloud); others only need to be unique within a resource group, subscription, or parent resource. Do not assume all resources share the same naming rules or endpoint patterns.

## 7. Common Endpoints When Integrating Spring Boot with Azure

The following table describes **Azure public cloud** with commonly used endpoints. National/sovereign clouds have different suffixes and authorities; services, regions, and network configurations can also change the actual endpoint. Always retrieve the exact endpoint from the resource's properties page or documentation for the current cloud environment.

| Managed Service | Typical Endpoint / Namespace | Common Azure SDK / Spring Integration | Notes |
| --- | --- | --- | --- |
| **Blob Storage** | `https://{account}.blob.core.windows.net` | Azure Storage Blob SDK; Spring Cloud Azure Blob starter | Account name differs from container name; blob path follows the host |
| **Service Bus** | `{namespace}.servicebus.windows.net` | Azure Service Bus SDK; Spring Cloud Azure Service Bus starter | Queues/topics are entities inside the namespace, not a mandatory hostname prefix |
| **Event Hubs** | `{namespace}.servicebus.windows.net` | Azure Event Hubs SDK; Spring Cloud Azure Event Hubs starter | Namespace endpoint may share the suffix format with Service Bus, but protocol/semantics differ |
| **Key Vault Secrets** | `https://{vault}.vault.azure.net/` | Azure Key Vault Secrets SDK; Spring Cloud Azure Key Vault starter | Requires appropriate secret read permissions; do not assume Keys/Certificates use the same API |
| **Azure App Configuration** | `https://{store}.azconfig.io` | Azure App Configuration SDK; Spring Cloud Azure App Configuration starter | Store endpoint differs from Key Vault endpoint |
| **Azure Cosmos DB (NoSQL)** | `https://{account}.documents.azure.com:443/` | Azure Cosmos SDK; Spring Data Cosmos | Endpoint may vary by API/environment; use the exact endpoint provided by the account |
| **Azure Resource Manager** | `https://management.azure.com` | ARM REST / Azure Resource Manager SDK | Management plane; typically requires subscription ID, RG, and resource ID |
| **Microsoft Entra authority** | `https://login.microsoftonline.com/{tenantId}` | Azure Identity SDK | Authentication authority; not a Blob or Service Bus data endpoint |

**Note on TLS and protocols:** some SDKs accept a **fully qualified namespace** (e.g., `ns.servicebus.windows.net`) instead of a URL starting with `https://`; other services require a full endpoint URL. Follow the exact parameter type expected by the SDK.

### Endpoints Do Not Always Contain Subscription or Resource Group

The host `stordersprod01.blob.core.windows.net` typically does not expose the subscription ID or resource group. Those belong to the **ARM management layer**, whereas the hostname is the data-plane connection address. This separation allows an application to access data via the endpoint once authorized, regardless of how the infrastructure team organizes subscriptions/RGs.

Do not guess an endpoint solely from a resource ID if the service has custom endpoints, multiple regions, a sovereign cloud, or private networking. Read the **endpoint published by the resource itself**.

## 8. Data Plane, Management Plane, and Permission Requirements

An application may use **two very different groups of APIs**:

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> B["Azure Identity\nTokenCredential"]
    A --> C["Azure SDK data client"]
    A --> D["ARM / management client"]
    B --> C
    B --> D
    C --> E["Service endpoint\nBlob / Service Bus / Key Vault"]
    D --> F["management.azure.com\nSubscription + RG + Resource"]
~~~

| Task | Plane | Typical Inputs Needed | Example Permission |
| --- | --- | --- | --- |
| Upload a blob to an existing container | **Data plane** | Blob endpoint, container/blob name, credential | **Storage Blob Data Contributor** at a sufficiently narrow scope |
| Receive messages from a Service Bus queue | **Data plane** | Namespace, queue name, credential | **Azure Service Bus Data Receiver** |
| Read a secret from Key Vault | **Data plane** | Vault URL, secret name, credential | **Key Vault Secrets User** when the vault uses the Azure RBAC permission model |
| Create a new storage account | **Management plane** | Subscription, resource group, location, resource configuration | Appropriate management role, e.g., Contributor at the required scope |
| Assign a role to a principal | **Management plane / IAM** | Scope resource ID, principal ID, role definition | Permission to create role assignments, typically part of an appropriate access administration role |

The **Reader/Contributor** roles on the ARM management plane do not necessarily grant data read/write permissions in Blob, Service Bus, or Key Vault. Some services have their own data-plane authorization mechanism (e.g., Cosmos DB for NoSQL). Verify the authorization model **per service** rather than treating all Azure roles as equivalent.

There are three independent questions before every request:

1. **Right target?** Endpoint, resource/account/namespace, container, or queue name.
2. **Right identity?** Credential actually selected, token-issuing tenant, token audience.
3. **Sufficient permissions and network path?** RBAC/policy, firewall, private DNS, TLS, routing.

## 9. Hands-on: Inspecting Azure CLI Context Before Integrating

With an account granted access permissions, the commands below help **observe** the currently selected tenant/subscription. Illustrative placeholders like `<subscription-id>` must be replaced with real IDs from your lab environment.

~~~bash
# Sign in to the Azure CLI using an identity permitted in the learning environment.
az login

# List the subscriptions visible to the Azure CLI.
az account list --output table

# View the subscription and tenant currently selected by the Azure CLI.
az account show --query "{subscription:id, tenant:tenantId, name:name}" --output json

# Switch the default subscription for subsequent Azure CLI commands.
az account set --subscription "<subscription-id>"

# Re-check before creating/managing resources.
az account show --query "{subscription:id, tenant:tenantId, name:name}" --output json
~~~

If you need to sign in to a specific tenant, you can use `az login --tenant "<tenant-id>"` according to your organization's policy. Headless environments require an appropriate non-interactive sign-in method; for application workloads, prefer managed identity or workload identity.

**Common pitfall:** `az account set` changes the **default subscription for CLI/ARM commands using that context**. It does not turn a Blob endpoint for account A into account B, does not automatically assign RBAC, and does not guarantee every SDK client will switch targets automatically. A data-plane SDK client still calls the endpoint it was configured with.

### Inspecting the Target Resource and Endpoint

~~~bash
# View the storage account in the selected resource group.
az storage account show \
  --name "<storage-account-name>" \
  --resource-group "<resource-group-name>" \
  --query "{id:id, location:location, name:name, endpoints:primaryEndpoints}" \
  --output json
~~~

This command reads **management-plane** information; it requires appropriate resource read permissions. If the account is in a different subscription, select the right subscription or pass `--subscription` if supported by the command. Do not rely on how a resource group name hints at a region; read the resource's `location` property.

## 10. Configuring Spring Boot with Endpoint and Identity

### 10.1. Spring Cloud Azure Starter Approach for Blob Storage

In a Spring Boot application that has selected a compatible **Spring Cloud Azure** version and added the **`com.azure.spring:spring-cloud-azure-starter-storage-blob`** starter, you can configure the account name via `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

For example, set `AZURE_STORAGE_ACCOUNT=stordersprod01`. For Azure public cloud and the default configuration mechanism matching the version, the starter can build the client for that storage account. If using a custom endpoint, emulator, or a different cloud environment, configure the endpoint/credential according to the **exact documentation of your Spring Cloud Azure version**.

The application uses the SDK client auto-configured by Spring:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.stereotype.Service;

@Service
public class DocumentLocator {

    private final BlobServiceClient blobServiceClient;

    public DocumentLocator(BlobServiceClient blobServiceClient) {
        this.blobServiceClient = blobServiceClient;
    }

    public BlobContainerClient documents() {
        return blobServiceClient.getBlobContainerClient("documents");
    }
}
~~~

This snippet only **obtains a client reference to the container**; the `documents` container must already exist if subsequent business logic operates on it. **Resource group and subscription ID do not appear** because Blob data-plane access does not directly use them to form the endpoint.

Credentials should come from mechanisms supported by Azure Identity and Spring Cloud Azure (e.g., developer login, workload identity, managed identity). Never commit storage account keys, connection strings, client secrets, or SAS tokens into `application.yml`.

### 10.2. Direct Azure SDK Approach

When you want explicit control over the endpoint, you can build a `BlobServiceClient` from `DefaultAzureCredential`. The dependencies are **azure-identity** and **azure-storage-blob**; manage versions consistently using an appropriate BOM.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobClientFactory {

    private BlobClientFactory() {}

    public static BlobServiceClient create(String blobEndpoint) {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(blobEndpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

Usage example:

~~~java
BlobServiceClient client = BlobClientFactory.create(
        "https://stordersprod01.blob.core.windows.net");
~~~

In a real Spring Boot application, declare the client as an application-scoped bean, load the endpoint from externalized configuration, and validate the URL format when appropriate. **DefaultAzureCredential** tries credential sources suitable for the environment; the selected identity must have data-plane permissions on that **exact storage account**.

Successfully instantiating `BlobServiceClient` usually only confirms that the client object configuration is valid; the actual request when reading/writing a Blob is what verifies connectivity, the token, and permissions at the service.

### 10.3. Why Not Pass Subscription ID to Every Client?

For a Blob data client, `endpoint + TokenCredential` is typically sufficient to identify the target and identity. If the same Spring Boot service needs to access Blobs in two subscriptions:

~~~text
Application principal
├── write role in subscription A / account stordersprod01
│   └── client A → https://stordersprod01.blob.core.windows.net
└── read role in subscription B / account stshareddata02
    └── client B → https://stshareddata02.blob.core.windows.net
~~~

You can create two clients with two different endpoints using the same credential, **if** the principal has the corresponding permissions on both resources and networking allows it. There is no need to change a subscription ID on every data API call; configure multiple clients explicitly and control roles per account.

For resource management APIs (creating a storage account, listing RGs, assigning roles), however, you must specify **subscription/resource group/scope** per the ARM SDK and have management-plane permissions.

## 11. Endpoints When Using Private Link / Private Endpoint

In production systems, the infrastructure team may disable public network access and use an **Azure Private Endpoint**. This is a network interface assigned a private IP inside a VNet to reach an Azure service over a private network path.

Crucially: **Private Endpoint changes the network path and how DNS resolves, not the meaning of tenant, subscription, or RBAC**.

Typically, the application still uses the **standard service hostname**, for example:

~~~text
stordersprod01.blob.core.windows.net
~~~

When the Private Endpoint and DNS are properly configured, that hostname can resolve through a `privatelink` alias/zone to the appropriate private IP from permitted network environments. Do not arbitrarily replace the standard hostname in source code with an IP address or a custom-made `privatelink` name: doing so can break TLS hostname validation or how the SDK identifies the endpoint.

To connect over a Private Endpoint, all of the following are required simultaneously:

- The Private Endpoint is created for the **exact service/subresource** (e.g., Blob, not a different Storage subresource).
- The VNet and workload have a network route to the private IP.
- The Private DNS zone and VNet links/forwarders are configured properly according to the architecture.
- Firewall/public network access settings and routes allow the intended traffic.
- The principal still holds the required data-plane permissions.

**Diagnostic symptom:** a developer calls Blob successfully from a laptop, while the app running inside a VNet times out; this usually points toward investigating DNS, routing, proxies, firewalls, or the Private Endpoint. Conversely, a successful connection returning 403 requires examining both authorization and the service's network policies. Do not deduce the cause from HTTP status alone while ignoring Azure logs/diagnostics.

## 12. Common Errors and How to Handle Them

| Symptom | Distinguishing Causes | How to Check |
| --- | --- | --- |
| Azure CLI creates resources in an unintended subscription | CLI currently has a different subscription selected | `az account show`, specify subscription ID explicitly in IaC |
| Can see the RG but not the expected storage account | Wrong subscription/RG, wrong name filter, or missing read permissions | Check actual resource ID, Reader/ARM permissions, and portal |
| SDK uses account A when account B is expected | Wrong `account-name` or injected endpoint | Print the normalized endpoint configuration (without exposing secrets), cross-check resource properties |
| Cannot acquire token or tenant error | Misconfigured credential chain/authority/tenant or workload identity | Identify the credential source, tenant, and actual app/client ID |
| Valid token yet upload returns **403** | Missing data role, wrong scope assignment, or network policy | Check **Storage Blob Data Contributor** on account/container, firewall, and response details |
| Key Vault secret read returns **403** | Wrong vault, wrong principal, or missing secret permission | Check vault URI, RBAC permission model / access policy, and role |
| Service Bus connects to namespace but send fails | Wrong queue/topic, missing sender role, or network | Check entity, **Azure Service Bus Data Sender** role, namespace hostname |
| Timeout inside VNet despite valid endpoint | Misconfigured Private DNS/route/firewall/proxy | Check DNS resolution from inside the workload, private IP, and network diagnostics |
| TLS certificate/hostname mismatch | Direct IP usage, custom endpoint, or misconfigured proxy | Use the hostname published by the service, verify TLS/SNI |
| Client creation succeeds but request fails | Client construction does not prove the service is reachable | Try a low-impact operation on a test resource, record the correlation ID |

Log **operation name, endpoint hostname, status code, Azure request ID/correlation ID, and response latency**, while masking sensitive details. **Never log access tokens, secrets, connection strings, SAS URLs, or credentials**. When sharing logs, ensure tenant/subscription/resource IDs do not violate organizational security policies.

### A Short, Ordered Debugging Workflow

1. **Verify target resource:** correct management tenant, subscription, RG, resource ID, and endpoint name.
2. **Verify caller:** which principal the runtime is executing as, and which credential is selected.
3. **Verify permissions:** role/data permissions on the exact account, container, namespace, or vault.
4. **Verify network:** DNS from where the app runs, ports/protocols, private endpoint, firewall, and proxy.
5. **Verify SDK/Spring configuration:** correct starter/version, properties, and injected client object.
6. **Reproduce with a minimal operation in a test environment:** read/write a test object and use the request ID to inspect service-side logs.

## 13. Multi-Subscription Architecture Example

Suppose an **Orders API** application runs in `sub-app-prod`, while shared data resides in `sub-data-prod`; both subscriptions currently belong to the same Entra tenant.

| Component | Where It Lives | Required Configuration |
| --- | --- | --- |
| Spring Boot Orders API | RG `rg-orders-app`, subscription `sub-app-prod` | Managed identity or workload identity |
| Storage account | RG `rg-orders-data`, subscription `sub-data-prod` | Blob endpoint + Storage Blob Data Contributor role for the app principal |
| Service Bus namespace | RG `rg-orders-data`, subscription `sub-data-prod` | Fully qualified namespace + Data Sender/Receiver roles per business flow |
| Key Vault | RG `rg-security`, subscription `sub-data-prod` or a dedicated security subscription | Vault URL + corresponding secret permissions |
| Private Endpoint and DNS | Aligned with workload networking | Routing and DNS from the app to service endpoints |

**Flow when Orders API writes a Blob:**

~~~mermaid
sequenceDiagram
    participant A as Orders API
    participant I as Azure Identity / Entra
    participant D as DNS / Network
    participant B as Azure Blob Storage
    A->>I: Request token for Azure Storage
    I-->>A: Access token for the identity
    A->>D: Resolve Blob hostname / connect
    D-->>A: Address and network path
    A->>B: HTTPS upload + token
    B->>B: Verify data permissions and access policies
    B-->>A: Success or detailed error code
~~~

**The workload's subscription does not dictate the data endpoint's subscription**. Access is evaluated based on identity, roles on the target resource, service policies, and network path. If the two subscriptions are in **different tenants**, you must design specific cross-tenant authentication/delegation rather than assuming this model works as-is.

## 14. Comparison with AWS and Google Cloud

| Question | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Which system do identities belong to? | Microsoft Entra tenant, principal, and managed/workload identity | IAM principal/role within an account and federation mechanisms | Google Cloud IAM principal, service account / workload identity |
| Typical governance and billing unit | Azure subscription | AWS account (optionally under AWS Organizations) | Google Cloud project, billing account, and organization/folder |
| Logical grouping of resources | Resource group | Tags, CloudFormation stacks, organizational constructs as needed | Project and resource hierarchy; labels, folders by goal |
| Resource identifier | ARM resource ID | ARN or service-specific ID | Fully qualified resource name/ID per service |
| Object storage access endpoint | Azure Blob account endpoint | Amazon S3 endpoint per region/access style | Cloud Storage endpoint/API |
| Access permissions | Azure RBAC and service-specific data-plane mechanisms | IAM policies and service-specific resource policies | IAM bindings and service-specific access conditions |

The similarity here lies in **the questions asked about identity, resources, permissions, and endpoints**, not an identical technical model. You cannot map an Azure resource group one-to-one to an AWS account or a Google Cloud project. When writing a multi-cloud abstraction, keep **provider**, **account/subscription/project context**, **resource locator**, **endpoint**, **credential**, and **permission model** clearly separated.

## 15. Lab Exercise

**Scenario:** Spring Boot receives a file and writes it to the `documents` Blob container. The application runs in subscription A, while the storage account may reside in subscription B.

1. Create or select a test storage account and `documents` container; record the **tenant ID**, **subscription ID**, **resource group**, **resource ID**, **account name**, and **Blob endpoint** in a separate lab environment sheet.
2. Sign in to the Azure CLI and use `az account show` to verify the subscription when inspecting account properties. Distinguish values used by the CLI from values needed by the SDK data client.
3. Use the **Spring Cloud Azure Blob starter** with `spring.cloud.azure.storage.blob.account-name`; configure externalized identity and grant **Storage Blob Data Contributor** at the appropriate test scope.
4. Write a service to upload a blob with a unique name. Verify that the request actually reaches the target account; do not assume success solely because the Spring context starts.
5. Intentionally configure a wrong account name, then change permissions from write to read-only in the test environment and observe the errors. Restore the proper configuration to complete the lab.
6. If a Private Endpoint is available in the lab, check DNS from where the application runs and compare the standard public host with the resolved IP in the private network.
7. Try accessing storage in subscription B (same tenant, with granted permissions); explain why **the right endpoint and the right role** are what matter, even without placing subscription B in the upload code.

### Self-Check Questions

- Can one subscription belong to multiple tenants simultaneously? Can one tenant manage multiple subscriptions?
- Must a resource group contain only resources in the same region?
- Why is `/subscriptions/.../resourceGroups/...` not a blob upload URL?
- Why does `az account set` not automatically change the target of an already-created `BlobServiceClient`?
- Does the resource-management **Contributor** role guarantee permission to read secrets or write blobs?
- When using a Private Endpoint, why does the application typically still use the standard service hostname?
- If Spring Boot receives 403, which three groups of causes must be distinguished before modifying code?

## 16. Key Takeaways

- **Tenant** is the identity boundary; **subscription** is the governance/billing scope; **resource group** is a logical/lifecycle grouping; **resource ID** identifies an ARM object; **endpoint** is the service communication address.
- **Data plane** typically requires the right endpoint, principal, permissions, and network path; **management plane** typically requires subscription/RG/resource ID plus ARM permissions.
- A resource in a different subscription can still be accessed by an application if identity, permission, and networking requirements are met; do not assume the same for different tenants.
- In Spring Boot, choose the appropriate Spring Cloud Azure starter or direct Azure SDK, load configuration from the environment, and avoid storing secrets in source code.
- When errors occur, check in order: **target resource → identity → RBAC/policy → DNS/network → SDK configuration**, using request IDs to aid diagnosis.

## References

- [Azure Resource Manager – Overview](https://learn.microsoft.com/azure/azure-resource-manager/management/overview)
- [Azure role-based access control – Overview](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Azure private endpoint DNS configuration](https://learn.microsoft.com/azure/private-link/private-endpoint-dns)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Azure Identity client library for Java](https://learn.microsoft.com/java/api/overview/azure/identity-readme)

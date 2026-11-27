# System-assigned and user-assigned managed identities

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, while learning how to deploy, monitor, secure, and control the cost of an application architecture on Azure. In the **Identity with Microsoft Entra ID** chapter, an essential question is: how can an application access Azure Key Vault, Storage, or Azure SQL without storing passwords or client secrets in source code?

**Managed identities** allow a workload running on Azure to obtain an access token issued by Microsoft Entra ID while Azure manages the identity's credentials on the platform side. There are two types: **system-assigned managed identity** and **user-assigned managed identity**.

After this lesson, you will be able to distinguish both identity types by lifecycle and reusability, assign appropriate access permissions, implement examples with Azure CLI and the Java SDK, diagnose errors, and design secure identities for a multi-environment system.

## 1. Why does a workload need an identity?

Suppose an orders API running on Azure App Service needs to read a secret from Azure Key Vault. If the API keeps a service principal's client secret in a configuration file, pipeline, or environment variable, the operations team must distribute, rotate, and protect that secret. If the credential leaks, an attacker can impersonate the application.

Managed identities solve the need to store long-lived credentials for **this Azure identity itself**: when a workload runs on a supported Azure service, Azure provides a token acquisition mechanism so the application can authenticate to target services. The Azure Identity SDK handles acquiring and refreshing tokens for the application.

```text
Application running on Azure
    |
    | (1) Requests an access token for the target service
    v
Azure managed identity mechanism
    |
    | (2) Authenticates workload via Microsoft Entra ID
    v
Access token for the workload identity
    |
    | (3) Sends token to Key Vault / Storage / Azure SQL
    v
Target service validates token and access permissions
    |
    +-- Sufficient permissions: executes operation
    +-- Missing permissions or conditions: denies access
```

The diagram describes the principle; token issuance endpoints and details depend on the workload host service and client library. Applications should generally use the official SDK rather than constructing raw HTTP calls to the token endpoint.

You must distinguish:

| Concept | Meaning | Example |
|---|---|---|
| **Identity** | Under what identity the workload is operating | Principal of the orders API |
| **Authentication** | The identity is verified to receive a token | Entra ID issues an access token |
| **Authorization** | What the principal is allowed to do on the target resource | Reading a specific secret in Key Vault |

**Enabling a managed identity does not automatically grant data-read permissions.** You still must assign permissions on the target service via Azure RBAC or the appropriate authorization model, as well as satisfy network restrictions and service policies.

## 2. Managed identities and Microsoft Entra ID

A managed identity is a workload identity, not an interactive human user account. Azure creates and manages a corresponding **service principal** in the Microsoft Entra ID tenant. When the workload calls a service supporting Entra ID, the application obtains a token representing that principal.

Important IDs:

| Name | Explanation | Purpose |
|---|---|---|
| `tenantId` | ID of the tenant containing the identity | Identifies the principal's tenant |
| `principalId` / Object ID | ID of the service principal in Entra ID | Used when assigning roles and verifying permissions |
| `clientId` | Identifier for the identity used by apps/SDKs | Helps select the right user-assigned identity |
| `id` / Azure Resource ID | Resource path of a user-assigned identity | Used to attach the identity to an Azure host |

Never mix up `principalId`, `clientId`, and Resource ID. For example, Azure CLI may require `--assignee-object-id` to be the principal ID when creating a role assignment, whereas `--identities` typically takes the Azure Resource ID of a user-assigned identity.

Managed identities are suited for **application-to-service** communication. They do not represent a signed-in end user; if an API must call a service on behalf of a user, you must design user authentication and delegated authorization separately.

## 3. System-assigned managed identity

A **system-assigned identity** is enabled directly on a supporting Azure resource, such as an Azure App Service, Function App, or virtual machine.

Lifecycle:

1. Create the resource hosting the application.
2. Enable system-assigned identity on the resource.
3. Azure creates and binds a platform-managed service principal.
4. Grant permissions to `principalId` on target services.
5. When the resource is deleted or the system-assigned identity is disabled, the identity tied to that resource is deleted.

Each resource can have at most **one system-assigned identity** of its own. This identity cannot be detached and reassigned directly to another resource. If you delete and recreate an App Service, the new principal ID may differ, so permissions granted to the old principal must be reconfigured.

**When to use:** an API with an independent lifecycle that only needs its own permissions, or a test environment created and torn down together as one resource set. System-assigned identities generally reduce the need to manage an extra Azure resource for the identity.

## 4. User-assigned managed identity

A **user-assigned identity** is created beforehand as an independent Azure resource in a resource group. You then explicitly assign it to one or more supported Azure resources.

Lifecycle:

1. Create the user-assigned identity resource, and Azure manages the corresponding principal in Entra ID.
2. Assign the identity to a supported Azure host.
3. Grant permissions to `principalId` on target services.
4. When replacing or deleting the host, the identity persists unless deleted separately.
5. You can assign that identity to another host when appropriate under security requirements and service support.

**When to use:** you need a stable principal across App Service replacements, or you need to intentionally share the same permission set across multiple workloads. Sharing also increases blast radius: if workload A is compromised, an attacker can exercise the shared identity's permissions that workload B also uses.

The name **user-assigned** refers to *an administrator creating and assigning the identity*. It is **not a personal user account** and does not require a human user to manually rotate a managed identity password.

## 5. Comparing the two managed identity types

| Criterion | System-assigned | User-assigned |
|---|---|---|
| How created | Enabled on an Azure resource | Created as a standalone Azure resource |
| Lifecycle | Tied to the host resource | Exists independently of the consuming resources |
| Deleting the host | Identity bound to the host is deleted | Standalone identity can continue existing |
| Assignable to multiple hosts | No | Yes, on supported hosts |
| How many a resource can use | At most one system-assigned | Multiple user-assigned if supported by the service |
| Token selection | Typically uses the resource's attached identity | Typically selected via `clientId` or an SDK-supported selector |
| Strengths | Fewer objects to manage, permissions tightly bound to workload | Stable principal, convenient for host replacement workflows |
| Primary risk | Recreating the resource requires re-granting roles to the new principal | Improper sharing can widen the permission blast radius |

Some Azure resources allow enabling a system-assigned identity while also assigning user-assigned identities. When multiple identities are present, the application must explicitly select the intended identity; a valid token for principal A does not give principal A the permissions of principal B.

Choose **system-assigned** if only one workload needs the permissions and the identity should disappear with the host. Choose **user-assigned** if the identity must survive host replacement or genuinely must be shared across multiple resources. If workloads require different permissions, prefer separate principals to follow least privilege.

## 6. RBAC: successful authentication does not guarantee access

After a managed identity obtains an access token, the target service validates both the token and the principal's permissions. The token must be issued for the exact **audience/resource**. A token for Azure Resource Manager does not automatically permit reading data in Key Vault.

With Azure RBAC, choose the **role** and **scope** matching the need:

| Need | Reference role | Scope to consider |
|---|---|---|
| Read secret values in Key Vault | `Key Vault Secrets User` | Specific Key Vault needed |
| Read blobs in Storage | `Storage Blob Data Reader` | Appropriate container or Storage Account |
| Read/write blobs | `Storage Blob Data Contributor` | Only the data scope needing write access |
| View resource management metadata | `Reader` | Corresponding resource or resource group |

**Control-plane** permissions (managing Azure resources) differ from **data-plane** permissions (reading/writing data inside a service). Assigning `Contributor` at the resource group does not automatically grant permission to read Key Vault secrets or blob data.

Azure Key Vault has two common permission models: **Azure RBAC** and **vault access policies**. The hands-on examples below assume Key Vault uses the **Azure RBAC permission model**. If a vault uses access policies, configure permissions according to the vault's model; an RBAC role assignment alone is insufficient to read secrets.

## 7. Hands-on: system-assigned identity for App Service

Suppose the `orders-api` running on Azure App Service needs to read a secret from Key Vault. The resource group, Web App, and Key Vault already exist. The operator has permission to configure identity on the Web App and assign roles on the vault. The following names are illustrative; replace them with real resources and verify the subscription before running:

```bash
APP_RG=rg-orders-prod-app
APP_NAME=app-orders-prod-001
VAULT_NAME=kv-orders-prod-001

az account show --output table
az account set --subscription "<subscription-id>"
```

### Step 1: Enable the identity

```bash
az webapp identity assign \
  --resource-group "$APP_RG" \
  --name "$APP_NAME"

az webapp identity show \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --output json
```

Retrieve the principal ID and the vault ID:

```bash
APP_PRINCIPAL_ID=$(az webapp identity show \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --query principalId --output tsv)

VAULT_RESOURCE_ID=$(az keyvault show \
  --name "$VAULT_NAME" \
  --query id --output tsv)
```

### Step 2: Check the permission model and grant permissions

```bash
az keyvault show \
  --name "$VAULT_NAME" \
  --query properties.enableRbacAuthorization \
  --output tsv
```

When the result is `true`, grant secret-read permission to the principal via RBAC:

```bash
az role assignment create \
  --assignee-object-id "$APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_RESOURCE_ID"
```

The scope is a specific vault, not the entire subscription. Role assignments can take some time to take full effect. If Key Vault uses access policies, apply the vault's corresponding permission management method instead of only running the command above.

### Step 3: Configure the Key Vault URL

```bash
az webapp config appsettings set \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --settings KEY_VAULT_URL="https://$VAULT_NAME.vault.azure.net/"
```

`KEY_VAULT_URL` is a service address, not a client secret. Application code will use the managed identity to acquire tokens.

### Step 4: Read the secret using the Azure SDK for Java

The Java application requires compatible `azure-identity` and `azure-security-keyvault-secrets` libraries. In an Azure environment with system-assigned identity enabled, you can use `DefaultAzureCredential`:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class OrdersSecrets {
    public static String readToken() {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("KEY_VAULT_URL is required");
        }

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();

        return client.getSecret("orders-service-token").getValue();
    }
}
```

The SDK uses the authentication source appropriate for the environment. On a developer workstation, `DefaultAzureCredential` may pick an account signed in through compatible developer tooling; on Azure, it can select the managed identity. Therefore, the local identity and the App Service identity **are not necessarily the same**. Grant permissions and verify them separately in each environment.

Never write secret values or access tokens to logs, stdout, error messages, or telemetry. If you need to ensure a production application uses only managed identity, you can explicitly choose `ManagedIdentityCredential` instead of the composite credential chain.

## 8. Hands-on: user-assigned identity with an independent lifecycle

Suppose the operations team will replace an App Service during an upgrade but wants the Key Vault access identity and its role assignments to remain intact. You can create a standalone user-assigned identity.

### Step 1: Create the identity and retrieve its identifiers

Assume the resource group for identities already exists:

```bash
IDENTITY_RG=rg-orders-prod-identities
IDENTITY_NAME=id-orders-prod-kv

az identity create \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --location southeastasia
```

Retrieve the Azure Resource ID, principal ID, and client ID:

```bash
UAMI_RESOURCE_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --query id --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --query principalId --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --query clientId --output tsv)
```

Distinguish their usage:

- `UAMI_RESOURCE_ID` is used to assign the identity to an Azure resource.
- `UAMI_PRINCIPAL_ID` is used as the assignee receiving permissions on target services.
- `UAMI_CLIENT_ID` lets the SDK select the right identity when a workload has multiple identities.

### Step 2: Assign the user-assigned identity to App Service

```bash
az webapp identity assign \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --identities "$UAMI_RESOURCE_ID"

az webapp identity show \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --output json
```

Inspect the `userAssignedIdentities` section in the output and confirm the right identity was assigned. If the resource also uses a system-assigned identity, verify the status of both identity types afterward. An Azure resource can only use identities and assignment methods supported by that service.

### Step 3: Grant secret-read permission to the user-assigned principal

```bash
az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_RESOURCE_ID"
```

Next, verify the role assignment at the vault scope. Because permissions are assigned to the **standalone identity**, they can remain valid when you replace the host and reassign that identity to the replacement workload. This does not eliminate requirements regarding network access, resource names, tenant, and service support.

### Step 4: Specify the identity for the application

Set the Client ID and vault URL in App Service configuration:

```bash
az webapp config appsettings set \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --settings AZURE_CLIENT_ID="$UAMI_CLIENT_ID" \
             KEY_VAULT_URL="https://$VAULT_NAME.vault.azure.net/"
```

In Java, you can select the identity by Client ID using `ManagedIdentityCredentialBuilder`:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class UserAssignedVaultClient {
    public static SecretClient create() {
        String clientId = System.getenv("AZURE_CLIENT_ID");
        String vaultUrl = System.getenv("KEY_VAULT_URL");

        if (clientId == null || clientId.isBlank()) {
            throw new IllegalStateException("AZURE_CLIENT_ID is required");
        }
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("KEY_VAULT_URL is required");
        }

        TokenCredential credential = new ManagedIdentityCredentialBuilder()
                .clientId(clientId)
                .build();

        return new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();
    }
}
```

`ManagedIdentityCredential` requires a host or environment supported by the SDK to acquire a managed identity token. Running this code on an ordinary laptop does not provide an Azure identity by itself. During local development, you can use `DefaultAzureCredential` with a signed-in developer account that has appropriate permissions.

If an application uses `DefaultAzureCredential` in Azure, `AZURE_CLIENT_ID` is a common way to specify the user-assigned managed identity. However, the `DefaultAzureCredential` chain may inspect other credential sources, so in production confirm which credential is actually selected and avoid redundant configuration that could shift the active principal.

## 9. Designing for multi-workload and multi-environment architectures

Suppose an e-commerce system has an API on App Service, an invoice-processing Azure Function, Azure Storage, and Key Vault. Each environment—dev, test, and production—must be managed and authorized separately.

A reference design:

| Workload | Recommended identity | Permissions | Rationale |
|---|---|---|---|
| `orders-api-dev` | Dedicated system-assigned | Read dev secrets and required data | Created/deleted together with the dev environment |
| `orders-api-prod` | Dedicated system-assigned | Read the API's production secrets | Isolated permissions for the API |
| `invoice-worker-prod` | Dedicated system-assigned | Only required invoice data or queues | Does not share the API's sensitive permissions |
| Old and new hosts during a planned workload replacement | Centrally managed user-assigned | Fixed permissions for that workload | Preserves principal during host transition |

In the example above, Key Vault can grant permissions to **multiple separate principals**. Two applications reading from the same vault are not forced to share one user-assigned identity.

Principles:

1. **Separate dev/test/prod:** an identity in dev must not have permissions to production data.
2. **Least privilege:** assign the smallest role and narrowest scope meeting the requirement.
3. **Clear ownership boundaries:** each identity should have a clear owner, purpose, list of target services, and consuming workloads.
4. **Infrastructure as Code:** manage identity assignments and role assignments in Bicep, ARM, or the organization's IaC tooling.
5. **Host replacement procedure:** update the list of resources assigned the identity, and verify token acquisition and actual permissions before retiring the old host.

Managed identities do not replace end-user authentication. If an application needs to know which employee is calling the API, it still must authenticate the user and enforce user authorization at the application layer.

## 10. Troubleshooting

Error messages typically help distinguish failure to acquire a token, acquiring a token but lacking permissions, and blocked network connectivity.

| Symptom | Likely cause | How to check |
|---|---|---|
| Managed identity not found | Identity not enabled/assigned, running on an unsupported host, or misconfigured | Check the resource's Identity blade and runtime environment |
| Wrong identity selected among multiple options | Missing Client ID or wrong identity specified | Specify the exact `AZURE_CLIENT_ID` / `clientId` and confirm identity assignment |
| Token acquired, but service returns `403 Forbidden` | Missing data-plane permission, wrong scope, vault uses access policy, or another policy denies access | Verify principal ID, role, scope, and permission model |
| Service returns `401 Unauthorized` | Missing token, wrong audience, expired, or invalid | Check how the SDK requests and sends the token |
| Correct role, yet cannot reach Key Vault | Firewall, private endpoint, DNS, or network route blocked | Check networking separately from identity checks |
| Role just granted, still denied | RBAC has not fully propagated or stale cached token | Check grant timestamp and retry after permissions propagate |
| Recreating App Service broke access | New system-assigned principal differs from old principal | Assign roles to the new principal via pipeline/IaC |
| Multiple workloads fail simultaneously after deleting an identity | A shared user-assigned identity was deleted | Inventory hosts sharing the identity and establish a replacement plan |

Ordered diagnostic workflow:

1. Identify where the workload runs, whether it supports managed identities, and which identities are enabled/assigned.
2. Identify the exact principal used by the SDK. Never print access tokens or secrets to logs for inspection.
3. Verify whether token acquisition succeeded. If it failed, focus on host, identity configuration, and client selector.
4. If token acquisition succeeded but the service call failed, inspect role assignments, scope, permission propagation time, and the target service's authorization model.
5. Check networking, DNS, firewalls, and private endpoints if the error relates to connectivity.
6. Correlate application logs, Azure Activity Log, and available service/Entra ID diagnostic logs.

Do not fix a `403` by granting `Owner` on the subscription or disabling all firewalls. Fix the exact principal, role, scope, or network issue.

## 11. Lifecycle and security principles

Managed identities eliminate storing a client secret to authenticate a workload, yet that does not make the workload immune to attack. If an attacker compromises the application, they can exercise whatever permissions the application's identity holds.

In operations:

- Restrict identity permissions using minimal roles and scopes; avoid sharing identities between applications with different trust levels.
- Never log access tokens, secret values, or sensitive data into logs, traces, or exceptions.
- Protect servers and deployment pipelines; control who may modify the application, assign identities, and create role assignments.
- Monitor RBAC and identity change history; periodically review unused permissions.
- Expect permission changes or revocations to take time to take effect due to active tokens or caches.
- Manage a user-assigned identity like any other resource with an owner, naming rules, tags, inventory tracking, and a retirement plan.

When deleting a **system-assigned identity**, the workload can no longer use that principal to obtain new tokens. Inspect and clean up unneeded role assignments. When deleting a **user-assigned identity**, inventory every resource using it and migrate them to a replacement identity per plan; deleting it prematurely can break multiple applications at once.

Managed identities require an Azure platform supporting the feature. Workloads running outside supported environments need another suitable Microsoft Entra ID authentication mechanism, such as workload identity federation where supported. Managed identities also do not automatically grant delegated permissions on behalf of end users.

## 12. Exercises and self-check questions

A company has two components:

- `orders-api` on App Service, which needs to read a secret in Key Vault.
- `orders-worker` on Azure Functions, which needs to read blobs in Storage; the company plans to replace the worker host frequently while keeping the same data-access principal.

Design the identity and permission setup:

1. Choose system-assigned or user-assigned for each workload and explain based on lifecycle.
2. State which ID is used to assign the identity to the host, which ID is used to assign roles, and which ID is used to select the identity in the SDK.
3. Propose roles and permission scopes for each workload.
4. Describe post-deployment verification steps, including token acquisition, calling the target service, and testing 403 behavior.
5. Describe the consequences of deleting a host using a system-assigned identity or deleting a shared user-assigned identity.

**Reference solution:** `orders-api` can use a system-assigned identity and the `Key Vault Secrets User` role on the target vault. `orders-worker` can use a user-assigned identity to preserve its principal across host replacements, assigned `Storage Blob Data Reader` at the appropriate Storage/Container scope. The two workloads do not need to share each other's permissions.

Answer for yourself:

- Is a user-assigned identity an employee's account?
- Why can successfully acquiring an access token still result in `403`?
- When replacing an App Service, what happens to its system-assigned identity?
- Why must Client ID be specified when multiple user-assigned identities exist?
- When should user-assigned identities be separated even if multiple apps use the same Key Vault?

The core answers, respectively, are: the identity is for workloads; target-service authorization is still required; the new host's principal may differ; the SDK must select the right identity; and separate them when applications have different permission sets, owners, or trust levels.

## 13. Pre-production checklist

- [ ] The Azure host supports the chosen managed identity type.
- [ ] The identity type is chosen based on resource lifecycle and reuse requirements.
- [ ] `principalId`, `clientId`, and Azure Resource ID are properly distinguished.
- [ ] The right role and scope are assigned on the target service.
- [ ] Control-plane and data-plane permissions are properly distinguished.
- [ ] The permission model of Key Vault or the corresponding service has been verified.
- [ ] Networking, firewalls, DNS, and private endpoints have been tested where applicable.
- [ ] The Azure Identity SDK is used, with no client secret embedded for the managed identity.
- [ ] The actual selected identity has been verified in each environment.
- [ ] Procedures exist for managing role assignments, host replacements, detaching, and deleting identities.

## Conclusion

Managed identities let workloads on Azure authenticate to services supporting Microsoft Entra ID without maintaining a client secret for that identity. **System-assigned** fits when an identity's lifecycle belongs to a single resource; **user-assigned** fits when an identity must exist independently or be intentionally reused.

Choosing the identity type is only the first step. A secure Azure application also requires proper data-plane permissions, appropriate RBAC scopes, network configuration, monitoring, and change procedures. When every identity has a clear purpose and owner, the system is far easier to govern and operate.

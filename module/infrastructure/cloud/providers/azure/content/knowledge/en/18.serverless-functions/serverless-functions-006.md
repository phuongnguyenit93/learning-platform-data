# Application Configuration, Secrets, and Managed Identity for Functions

An Azure Function might contain only a few lines of code handling an HTTP request, queue event, or uploaded file. In real operations, however, Functions routinely need external API URLs, feature flags, environment settings, Storage connection info, and access to Azure Key Vault, databases, or message brokers. Embedding all of that in source code makes promoting between dev/staging/production difficult, complicates key rotation, and risks accidentally leaking secrets during builds, deployments, or logging.

**Azure Functions app settings** decouple configuration from code. **Azure Key Vault** stores and governs secrets under policy. **Managed identity** gives a Function App a Microsoft Entra ID identity to access many Azure services without managing passwords or long-lived client secrets.

This lesson belongs to the **Serverless with Azure Functions** chapter in the **CLOUD_PROVIDERS_AZURE** module. The content ties into Subscriptions, Resource Groups, Microsoft Entra ID, virtual networks, Storage, serverless apps, Azure Monitor, and cost management. The focus is turning a Function from a prototype with hardcoded connection strings into a service with clean configuration, least-privilege permissions, auditability, and reliable operations.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between application settings, environment variables, connection strings, secrets, Key Vault references, and managed identities.
2. Configure Azure Functions locally via `local.settings.json` and in Azure via Function App settings.
3. Recognize essential runtime settings, especially `FUNCTIONS_WORKER_RUNTIME` and `AzureWebJobsStorage`.
4. Choose system-assigned or user-assigned managed identities for the right use cases.
5. Grant least-privilege data permissions using Azure RBAC for Key Vault, Blob Storage, Queue Storage, and supported services.
6. Use Key Vault references or SDKs with `DefaultAzureCredential`/`ManagedIdentityCredential` without putting real secrets into source.
7. Explain identity-based connections for Functions triggers/bindings and their extension/hosting-plan prerequisites.
8. Implement configuration workflows, secret rotation, 401/403/DNS troubleshooting, and safe log inspection.
9. Design production checklists, environment isolation, CI/CD security, and cost monitoring.

The Azure CLI commands below are examples; they do not run on their own and must be adapted to your Azure subscription, runtime, hosting plan, region, and organizational policies.

## 2. Three Problems to Solve Separately

### 2.1. Configuration Is Not Always a Secret

An application might need values such as:

| Example | Classification | Typically Appropriate Place to Manage |
|---|---|---|
| APP_ENV=production | Non-secret configuration | Function App settings |
| API_TIMEOUT_SECONDS=20 | Non-secret configuration | Function App settings |
| FEATURE_PROCESS_V2=false | Feature flag | App settings or feature management service |
| STORAGE_BLOB_URI=https://...blob.core.windows.net/ | Service endpoint; normally not a credential | App settings |
| Database password | Secret | Key Vault or identity-based access when possible |
| Third-party API token | Secret | Key Vault |
| Storage Account key | Broad-privilege credential | Avoid when Entra identity is supported; if required, manage strictly as a secret |
| Managed identity Client ID | Identifier, normally not a password | App setting per design |
| Azure Function host key | Key for certain HTTP/webhook scenarios | Store only in secure server-side locations, never in public clients |

**The path to a secret is not necessarily a secret**, though vault names, account names, resource IDs, and internal topology still must follow your organization's data classification rules.

### 2.2. Secrets and Identities Solve Two Different Problems

- **Secret:** a sensitive value requiring protection, such as an API token for a provider that does not support Microsoft Entra ID.
- **Managed identity:** an Azure-managed identity for a resource; it enables obtaining access tokens for services that accept Entra ID and enforce Azure RBAC.
- **App setting:** the mechanism distributing configuration values into the Function runtime, which can hold plain strings or Key Vault references.
- **Key Vault reference:** a syntax in an app setting allowing the App Service/Functions platform to resolve the target secret and inject its value into the app per supported mechanics.
- **Direct Key Vault SDK call:** an alternative where the app uses its identity to call the Key Vault API, owning caching, error handling, and refresh timing itself.

A Function using managed identity to get an Azure Storage token may need zero Storage key secrets. However, if it calls a third-party API supporting only static API keys, the Function still needs that secret stored appropriately.

### 2.3. Caller Authentication Differs from Outbound Identity

~~~mermaid
flowchart LR
    C["Client / Event Source"] -->|HTTP/trigger| F["Azure Function"]
    E["App Settings"] -.-> F
    F -->|Managed Identity token| S["Blob / Queue / Key Vault"]
    F -->|API key from Key Vault if required| X["Third-party service"]
    I["Microsoft Entra ID"] -. "Issues access token" .-> F
~~~

**Do not confuse them:**

- **Inbound authentication:** who is allowed to invoke the HTTP Function? This involves Function keys, App Service Authentication, API Management, or application-level auth.
- **Outbound authorization:** which Blobs can the Function read, which Queue messages can it receive, or which secrets can it fetch? This relies on managed identity, Azure RBAC, and target-service data policies.

Enabling managed identity **does not automatically make an HTTP endpoint private or require Entra tokens from callers**. Endpoint protection must be configured separately.

## 3. How Does Azure Functions Receive Configuration?

### 3.1. Multi-Environment Configuration Model

~~~mermaid
flowchart TD
    G["Source code / artifact"] --> D["Dev Function"]
    G --> T["Staging Function / slot"]
    G --> P["Production Function"]
    LD["local.settings.json<br/>for development only"] -.-> D
    SD["Dev settings / dev identity"] -.-> D
    ST["Staging settings / identity"] -.-> T
    SP["Production settings / identity"] -.-> P
    KV["Environment-specific Key Vault and RBAC"] -.-> T
    KV -.-> P
~~~

The goal is promoting the **same tested artifact** across environments where compatible, while endpoints, permissions, resource IDs, and secrets are supplied per environment. Never bake production passwords into zip packages, container images, or source code.

### 3.2. `local.settings.json`

When running Azure Functions Core Tools locally, projects typically include `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "APP_ENV": "local",
    "API_TIMEOUT_SECONDS": "20",
    "DOCUMENTS_BLOB_URI": "http://127.0.0.1:10000/devstoreaccount1"
  }
}
~~~

Explanation:

- **IsEncrypted** tells Core Tools whether local values are encrypted; setting it to `false` does not make the file a secure secret store.
- **Values** contains key/value pairs consumed by the runtime.
- **FUNCTIONS_WORKER_RUNTIME** selects the language worker, such as `python`, `node`, or `dotnet-isolated` depending on the app.
- **AzureWebJobsStorage=UseDevelopmentStorage=true** points to a storage emulator like Azurite for supported features.
- **APP_ENV** and **API_TIMEOUT_SECONDS** are user-defined application settings.

JSON values inside `Values` should be strings to match how the runtime injects environment variables. Storage triggers/bindings may require Azurite or real services depending on type; do not assume the emulator supports every Azure Storage feature.

**Important:** `local.settings.json` can contain connection strings or passwords on a dev machine, so:

1. Never commit a file containing real values to Git.
2. Provide a `local.settings.json.example` or docs with non-sensitive placeholders if needed.
3. Restrict file read permissions on the machine.
4. Never upload this file as part of a deployment artifact.
5. If a credential is exposed, revoke/rotate it rather than just deleting the line from Git.
6. When using Entra credentials locally, prefer approved developer sign-in flows with least-privilege dev permissions.

### 3.3. Configuration in Azure

When running in Azure, Function App settings are exposed as environment variables/app configuration per the runtime. They can be managed via Azure Portal, Azure CLI, Bicep/Terraform, or pipelines.

Example:

~~~text
APP_ENV=production
API_TIMEOUT_SECONDS=20
DOCUMENTS_BLOB_URI=https://stordersprod.blob.core.windows.net/
THIRD_PARTY_API_KEY=@Microsoft.KeyVault(...)
~~~

Never treat `local.settings.json` as a production configuration source. Special settings managed by the Azure Functions platform or hosting plan behave differently from ordinary app settings. Updating app settings can restart the Function App or recycle worker instances, so production changes need controlled change management and post-deploy verification.

### 3.4. Core Platform Keys to Recognize

| Setting | Purpose | Notes |
|---|---|---|
| FUNCTIONS_WORKER_RUNTIME | Selects the language worker | Must match runtime and artifact |
| FUNCTIONS_EXTENSION_VERSION | Selects supported Functions runtime major version, typically `~4` in modern setups | Never upgrade blindly without compatibility testing |
| AzureWebJobsStorage | Functions host Storage connection | Can use connection string or identity-based config depending on plan/runtime |
| APP_ENV | Optional application setting | Carries no automatic Azure semantics unless read by app code |
| WEBSITE_RUN_FROM_PACKAGE | Controls running from package in applicable plans/scenarios | Do not add blindly to every plan; check Flex Consumption specifically |
| WEBSITE_CONTENTAZUREFILECONNECTIONSTRING, WEBSITE_CONTENTSHARE | Content storage settings on certain hosting plans | Not identical across all Functions plans; do not delete blindly when switching to managed identity |
| APPLICATIONINSIGHTS_CONNECTION_STRING | Telemetry connection config | Not a credential to call arbitrary APIs |
| AzureWebJobs.<FunctionName>.Disabled | Can disable a specific Function where supported | Watch triggers when using slots and setting changes |

**Do not turn every setting into a secret.** Only true secrets belong in a vault. Non-secret configuration belongs in reviewed IaC or app settings for clear change tracking.

### 3.5. Naming and Hierarchical Configuration

For identity-based connections, Azure Functions uses groups of app settings sharing a **common prefix**, for example:

~~~text
AzureWebJobsStorage__accountName
OrdersStorage__queueServiceUri
OrdersStorage__credential
OrdersStorage__clientId
~~~

The double underscore is part of prefix-based configuration, distinct from a single setting holding a connection string. In .NET apps and environment variables, double underscores also commonly represent hierarchical configuration, though exact parsing depends on the runtime, SDK, and extension.

Do not write code assuming double underscores mean the exact same thing to every library. For Functions triggers and bindings, follow the connection schema defined by each extension.

## 4. Secrets: Where to Put Them and Where Not To

### 4.1. Common Places Secrets Leak

Risks commonly arise from:

- Hardcoding passwords in source code or Dockerfiles.
- Committing `local.settings.json` with real tokens.
- Passing keys as CLI arguments while shell history or debug tracing is active.
- Printing environment variables to Application Insights or CI/CD logs.
- Returning secrets in HTTP responses when debug mode is enabled.
- Putting credentials in URL query strings.
- Sharing one account key across dev, staging, and production.
- Granting broad Key Vault permissions instead of only the needed secrets.

Git history retains old commits even after removing a secret line from the current branch. Always perform **rotation/revocation** when exposure is suspected.

### 4.2. Azure Key Vault

Azure Key Vault manages **secrets**, **keys**, and **certificates**, which are distinct object types. This lesson focuses on secrets such as API keys.

A sound workflow:

1. Provision a vault in a governed subscription and resource group.
2. Select the permission model (Azure RBAC or vault access policies) per organizational standards.
3. Name secrets clearly and apply data classification.
4. Grant the Function identity least-privilege access to read only required secrets.
5. Configure network access, firewalls, or private endpoints as required.
6. Reference secrets from Function settings or call the Key Vault SDK.
7. Establish monitoring, secret lifecycle rules, and revocation runbooks.

Do not use Key Vault merely as a dumping ground for every environment variable without access policies or lifecycle management.

### 4.3. How Key Vault References and Direct SDK Calls Differ

| Aspect | Key Vault Reference in App Setting | Direct Key Vault SDK Call |
|---|---|---|
| Application code | Reads app setting like ordinary config | App calls Key Vault explicitly |
| Identity mechanism | Platform uses configured reference identity | SDK uses credential chain or managed identity |
| Caching/refresh | Handled by App Service/Functions platform refresh cycle | App designs its own cache, retries, and refresh |
| Common errors | Unresolved reference, insufficient identity or network access | SDK receives 401/403/timeouts, retry/auth issues |
| Flexibility | Convenient for static secrets consumed as app settings | Useful for querying many secrets or dynamic selection |
| Traceability | Must inspect reference resolution status and platform logs | App can track dependency calls and classify errors directly |

**Key Vault references resolve into secret values inside the app process environment.** You must still protect environment dumps, diagnostic endpoints, debug tools, and access to the Function App. Using a vault does not remove plaintext from process memory when the app uses it.

## 5. What Is a Managed Identity?

### 5.1. Core Concept

A managed identity binds a Microsoft Entra ID–managed identity to an Azure resource. Applications can acquire access tokens for Entra-enabled services without storing client secrets or certificates like a traditional service principal.

~~~mermaid
sequenceDiagram
    participant F as Azure Function
    participant M as Managed Identity endpoint
    participant E as Microsoft Entra ID
    participant S as Azure Storage / Key Vault
    F->>M: Request token for resource/scope
    M->>E: Exchange platform identity
    E-->>M: Access token
    M-->>F: Short-lived token
    F->>S: Call API with token
    S->>S: Validate token + check permissions
    S-->>F: 200 or auth/authz error
~~~

This diagram shows the logical flow. Token endpoints and low-level details are managed by the Azure platform; apps should use Azure Identity SDKs instead of hand-rolling token protocols.

**Having a managed identity does not grant data permissions.** After enabling the identity, you must still assign roles or permissions on Storage, Key Vault, Service Bus, databases, or target services.

### 5.2. System-Assigned vs. User-Assigned

| Criterion | System-Assigned Managed Identity | User-Assigned Managed Identity |
|---|---|---|
| Lifecycle | Tied to the Function App resource | Independent Azure resource |
| When Function App is deleted | Corresponding system identity is deleted | User-assigned identity can remain |
| Reuse | Dedicated to one specific Function App | Can be attached to multiple supported resources |
| Complexity | Simple for standalone apps | Requires managing separate identity resources and lifecycles |
| Principal/object ID | Tied to app's identity; changes if recreated | Belongs to the independent identity resource |
| Use case | A single Function App accessing its own Storage and vault | Multiple Function Apps, slots, or workloads needing pre-created/shared governed identities |

Do not assume reusing one user-assigned identity across many apps is safer: sharing an identity enlarges the **blast radius** if one app is compromised. Share only when permissions and lifecycles truly belong together.

### 5.3. App Identity and Entra Users Are Distinct Principals

- **User:** engineer signing into the Azure Portal or CLI.
- **CI/CD identity:** pipeline identity authorized to update the Function App.
- **Function managed identity:** identity used by code inside the Function to call services.
- **HTTP caller identity:** user or service invoking the Function's endpoint.
- **External service account/credential:** third-party authentication mechanism.

Never grant every permission to the same principal out of convenience. A pipeline that deploys code should not automatically read runtime secrets, and a Function does not need Resource Group Owner just to read a blob.

## 6. Lab 1: Enabling System-Assigned Identity

Assume the Function App **func-orders-prod** in resource group **rg-functions-prod** already exists with a compatible hosting plan and runtime.

### 6.1. Verify Subscription and Function App

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az functionapp show \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --query "{name:name,state:state,kind:kind,identity:identity}" \
  --output json
~~~

The `show` command may return identity fields in varying structures depending on API version; confirm the Function App exists in the right subscription and tenant. Never provision a new production app just while trying to inspect one.

### 6.2. Enable the Identity

~~~bash
az functionapp identity assign \
  --resource-group rg-functions-prod \
  --name func-orders-prod
~~~

Retrieve the principal ID:

~~~bash
PRINCIPAL_ID=$(az functionapp identity show \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --query principalId --output tsv)

echo "$PRINCIPAL_ID"
~~~

**principalId/object ID** is the identifier normally used for Azure role assignments. **clientId** identifies the app/managed identity in other contexts; do not swap `clientId` for `object ID` across CLI flags blindly.

Once created, the identity still has zero permissions on target services. Identity and role assignment changes can take time to propagate through Entra and RBAC.

### 6.3. Grant Read-Only Access to Blob Storage

Assume a Storage account holds a documents container the Function only needs to read. Retrieve the account resource ID:

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group rg-data-prod \
  --name stordersdata01 \
  --query id --output tsv)

echo "$STORAGE_ID"
~~~

Assign the Blob data role:

~~~bash
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_ID"
~~~

**Storage Blob Data Reader** fits Blob read operations within the granted scope rather than all Storage operations. In production, narrow scope to a specific container when supported by tools and permissions. Also check whether broader inherited role assignments exist.

### 6.4. Verify Assigned Permissions

~~~bash
az role assignment list \
  --assignee-object-id "$PRINCIPAL_ID" \
  --scope "$STORAGE_ID" \
  --include-inherited \
  --output table
~~~

Seeing a role assignment does not prove network connectivity to Blob works; verify the network path, effective permissions, and actual SDK calls.

Never fix a 403 error by assigning Contributor across the subscription. Distinguish **data-plane roles** for Blob access from **management-plane** Azure roles managing the Storage Account itself.

## 7. Lab 2: Referencing a Secret from Key Vault

### 7.1. Choose a Clear Permission Model

Key Vault supports different authorization models depending on configuration, commonly **Azure RBAC** and **Vault access policies**. Do not mix the two haphazardly.

The examples below assume vault **kv-orders-prod** uses the Azure RBAC permission model. If the vault uses access policies, grant permissions using the active vault model rather than assigning RBAC roles and expecting them to govern the data plane.

**Never switch a production vault's permission model** just to follow a tutorial, as that can break permissions for other applications.

### 7.2. Grant Secret Read Access to the Function

~~~bash
VAULT_ID=$(az keyvault show \
  --resource-group rg-security-prod \
  --name kv-orders-prod \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
~~~

This role allows reading secret values within the granted scope under Key Vault RBAC. Narrow scope further when required and supported, and check inherited permissions.

Roles such as `Key Vault Reader` **do not by default allow reading secret values**; role names are easy to confuse between metadata and secret payloads.

### 7.3. Create Secrets Safely

Suppose a third-party API issues a token. An operator authorized to write secrets uses an organization-approved workflow to store it in the vault.

To avoid leaking secrets into shell history, logs, or process command lines, this lesson **omits CLI commands passing real tokens as arguments**. Use an approved secret provisioning/automation workflow with vault permissions; each environment should use secure input handling.

Example secret layout:

~~~text
Vault: kv-orders-prod
Secret: partner-api-token
Secret value: [stored via secret management workflow]
~~~

When choosing between pinning a specific version or referencing the latest version, understand the trade-offs. A version-pinned reference will not automatically switch to a new version upon secret rotation.

### 7.4. Put the Key Vault Reference in a Function App Setting

Common platform syntax:

~~~text
@Microsoft.KeyVault(VaultName=kv-orders-prod;SecretName=partner-api-token)
~~~

Or using `SecretUri` with a Key Vault secret identifier:

~~~text
@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/partner-api-token/<SECRET_VERSION>)
~~~

CLI example (contains no secret value):

~~~bash
az functionapp config appsettings set \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --settings 'PARTNER_API_TOKEN=@Microsoft.KeyVault(VaultName=kv-orders-prod;SecretName=partner-api-token)' \
  --query '[].{name:name,slotSetting:slotSetting}' \
  --output table
~~~

Use single quotes in Bash so the semicolon stays inside one argument. **Windows PowerShell has different quoting rules**; test exact string passing before embedding in pipelines.

Key Vault references default to **system-assigned identity in many supported scenarios**; to use a user-assigned identity, set the Function App's `keyVaultReferenceIdentity` property per documentation. Never assume simply attaching a user-assigned identity redirects Key Vault references to it automatically.

### 7.5. Reading the Secret in Code

In code, once the platform resolves the reference as supported, the application simply reads the setting:

~~~python
import os

PARTNER_API_TOKEN = os.environ["PARTNER_API_TOKEN"]
~~~

**Never** print the token to the console or return it in an HTTP response. If a Key Vault reference fails to resolve due to identity, permission, or network issues, reading the setting may yield unexpected values; the app must fail safely rather than calling an API with an unresolved `@Microsoft.KeyVault(...)` string.

For Functions with multiple triggers or instances, consider refresh timing and config reload behavior when secrets change. Never assume every individual request immediately fetches a newly rotated secret.

### 7.6. Refresh Timing and Rotation

Key Vault references are cached and refreshed by the App Service/Functions platform. Updating a secret in the vault **does not guarantee all workers immediately receive the new value**. In common scenarios, unversioned references refresh on a cycle of up to roughly 24 hours; configuration updates or supported refresh actions can trigger earlier re-resolution.

Recommended rotation workflow:

1. Create a new secret version or issue a new credential at the third-party provider.
2. Maintain a transition window accepting both old and new keys if the provider supports it.
3. Update/refresh the reference via approved mechanisms.
4. Verify the Function with safe health/transaction checks and monitor for errors.
5. Revoke the old key after confirming all clients have switched over.
6. Record the change log, UTC timestamp, and verification evidence.

If the provider supports only one active token at a time, plan a maintenance/cutover window and rollback strategy. Never delete the old secret before a recovery path exists.

## 8. User-Assigned Identity and Key Vault References

### 8.1. When Do You Need a User-Assigned Identity?

A user-assigned identity fits when you:

- Want identity lifecycles managed independently from the Function App.
- Need the identity to exist before the Function App starts or references secrets.
- Frequently redeploy or recreate Function Apps while keeping the principal/role assignments stable.
- Share one governed identity across multiple resources that genuinely have the **same purpose and permissions**.
- Have hosting or Key Vault reference workflows requiring the identity ahead of resource provisioning.

Never share one user-assigned identity across every function app just to reduce role assignment count; an over-privileged shared identity exposes every attached app to a larger blast radius.

### 8.2. Create a User-Assigned Identity

~~~bash
az identity create \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --location southeastasia
~~~

Retrieve its identifiers:

~~~bash
UAMI_ID=$(az identity show \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --query id --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --query clientId --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group rg-identity-prod \
  --name id-func-orders \
  --query principalId --output tsv)
~~~

These three values are distinct:

- **Resource ID:** Azure Resource Manager identifier for the identity resource.
- **Client ID:** selects the right managed identity when an app or SDK sees multiple identities.
- **Principal ID:** object/principal target for Azure RBAC role assignments.

Assign the identity to the Function App:

~~~bash
az functionapp identity assign \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --identities "$UAMI_ID"
~~~

Next, grant least-privilege roles to **`UAMI_PRINCIPAL_ID`** on target resources. If Key Vault references should use the user-assigned identity, configure **`keyVaultReferenceIdentity`** with its resource ID via Portal/ARM/IaC or supported tooling and verify it.

### 8.3. Selecting the Right Identity in the SDK

For a user-assigned identity, Azure SDKs typically let you target it by client ID. For example, set:

~~~text
AZURE_CLIENT_ID=<UAMI_CLIENT_ID>
~~~

In Azure Identity–enabled SDKs, `AZURE_CLIENT_ID` tells `DefaultAzureCredential` which managed identity to select in Azure. Never mix up one identity's client ID with another identity's principal ID.

With system-assigned identity, specifying a client ID is usually unnecessary. If multiple identities are attached to one Function App, explicitly configure which credential/identity the app uses rather than relying on ambiguous default selection.

## 9. Illustrative Code: Python Function Reading Blobs via Identity

### 9.1. Why Isn't a Storage Account Key Needed?

A Function holding **Storage Blob Data Reader** can use a Microsoft Entra access token via the Azure SDK to read Blobs. The app does not need an Account key for supported Blob reads.

The example below assumes:

- The Function App has an active managed identity.
- The identity holds read permissions on the Blob/container.
- The Storage account endpoint is reachable over the network.
- `azure-identity` and `azure-storage-blob` are listed in dependencies.
- Code does not construct `BlobServiceClient` from keys or connection strings.

### 9.2. Minimal Python Code

~~~python
import os

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

def read_small_text_document(blob_name: str) -> str:
    # Use only for small documents with validated names.
    account_url = os.environ["DOCUMENTS_BLOB_URI"]

    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=account_url,
        credential=credential,
    )
    blob = blob_service.get_blob_client(
        container="documents",
        blob=blob_name,
    )

    content = blob.download_blob().readall()
    return content.decode("utf-8")
~~~

This snippet demonstrates the credential flow, not a complete production HTTP Function endpoint. Real applications must:

- Validate inputs/blob names so users cannot read arbitrary files.
- Authenticate callers and enforce application-level authorization.
- Handle `BlobNotFound`, 403, 429, timeouts, and retries as appropriate.
- Avoid loading huge Blobs completely into RAM.
- Reuse clients/credentials sensibly rather than recreating everything per invocation where appropriate.
- Avoid logging sensitive document contents.

**`DefaultAzureCredential`** walks different credential chains locally vs. in Azure (developer login, environment variables, managed identity, etc.). This is convenient across dev/prod, yet requires verifying your active environment and identity so developer privileges are never relied upon unexpectedly.

### 9.3. Non-Secret Configuration for the SDK

~~~bash
az functionapp config appsettings set \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --settings DOCUMENTS_BLOB_URI=https://stordersdata01.blob.core.windows.net/ \
  --query '[].{name:name}' \
  --output table
~~~

This value is a service URI, not a secret. If the Storage Account uses a private endpoint and blocks public access, the URI keeps the standard service hostname while private DNS/networking routes it to the private destination.

### 9.4. Running Locally

Sign in to Azure CLI with an appropriate dev account or use an approved developer identity mechanism, granting dev permissions on **dev resources**—never production Contributor for convenience.

Verify which principal the credential actually picked. When code works locally but fails with 403 in production, it is usually two different identities holding different role assignments.

## 10. Identity-Based Connections for Triggers and Bindings

### 10.1. Difference Between SDKs and Functions Bindings

The SDK example above explicitly creates a `BlobServiceClient` using Azure Identity. By contrast, an Azure Function can use **triggers/bindings** such as `QueueTrigger`, `BlobTrigger`, or input bindings, where extensions establish connections and authenticate on the app's behalf.

Consequently, configuring SDK code does not automatically make triggers use managed identity. You must use an **extension version that supports identity-based connections** and declare the exact connection prefix, service URI, roles, and hosting-plan requirements.

### 10.2. `QueueTrigger` Example in Python v2

Suppose `function_app.py` has:

~~~python
import azure.functions as func
import logging

app = func.FunctionApp()

@app.queue_trigger(
    arg_name="message",
    queue_name="orders-pending",
    connection="OrdersQueue",
)
def process_order(message: func.QueueMessage) -> None:
    logging.info("Received an order message")
    # Invoke business layer; do not log full payload if it contains sensitive data.
~~~

In the decorator, **`connection="OrdersQueue"`** specifies only the connection setting prefix. It should never hold an actual connection string or token.

If your app's extension and hosting plan support identity-based queue connections, app settings look like:

~~~text
OrdersQueue__queueServiceUri=https://stordersqueue01.queue.core.windows.net/
~~~

If using a supported user-assigned managed identity:

~~~text
OrdersQueue__credential=managedidentity
OrdersQueue__clientId=<UAMI_CLIENT_ID>
~~~

Exact setting names, default system-assigned identity behavior, and extra fields depend on the Storage Queue extension and Functions runtime version. **Do not keep an exact-match connection string named `OrdersQueue` at the same time** when migrating to prefix-based identity settings: exact matches may take precedence and make the binding keep using the connection string.

The identity driving `QueueTrigger` needs full queue processing permissions, not just metadata read access. The data-plane role may be **Storage Queue Data Contributor** or granular roles suited to your service/feature operations. Check the current permission matrix and test actual message reads and deletions.

### 10.3. `BlobTrigger` Can Require Multiple Permission Types

A `BlobTrigger` may need permissions to read source blobs, write checkpoints/receipts, use internal queues, or interact with host-supporting services depending on the extension and mode. Therefore:

- Do not assume `Storage Blob Data Reader` always covers every `BlobTrigger`.
- Distinguish the connection used to **read blobs** from the connection used for **host state**.
- Verify extension version 5.x or the version supporting identity-based access.
- Distinguish event-based `BlobTrigger` from polling modes where supported by the extension.
- Assign the right data roles and inspect trigger logs.
- Test with real files in a dev container before removing connection strings.

The Functions host's **`AzureWebJobsStorage`** connection and the binding's **`OrdersQueue`** connection serve distinct purposes even when they occasionally point to the same Storage Account.

### 10.4. Other Services

| Trigger/Binding | Permissions to Inspect | Key Prerequisites |
|---|---|---|
| Azure Queue Storage | Queue data-plane | Extension supports identity-based config and trigger actions |
| Azure Blob Storage | Blob data-plane, possibly host/queue permissions | Checkpoints/receipts and trigger mode |
| Azure Service Bus | Service Bus Data Receiver/Sender by direction | Namespace/entity permissions, extension, and network |
| Azure Event Hubs | Event Hubs Data Receiver/Sender by role | Consumer group, checkpoint store, scaling |
| Azure Cosmos DB | Matching data-plane RBAC | SDK/extension support and container/database permissions |
| Azure SQL | Entra authentication/SQL permissions | Driver/connection mode and contained database user |
| HTTP trigger | Inbound protection per design | Never expect outbound managed identity to authenticate callers |

Many Azure services separate management-plane Azure RBAC from data-plane permissions. A Resource Group Contributor role does not replace data-plane access rights needed by runtime connections.

## 11. `AzureWebJobsStorage`: Special Connection for the Functions Host

### 11.1. What Is Host Storage Used For?

The Azure Functions runtime needs Storage in many scenarios to maintain operational state, locks/leases, and data supporting host/trigger behavior, depending on hosting plan and trigger types.

In legacy setups or default deployments, the setting looks like:

~~~text
AzureWebJobsStorage=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
~~~

This is a storage connection string containing an account key; **never put real values into exercises or repositories**. Several hosting/runtime versions support or encourage configuring host storage with managed identity to eliminate key dependencies.

Never delete `AzureWebJobsStorage` from a Function App without a valid equivalent replacement; triggers may stop firing or the host may fail to start.

### 11.2. Identity-Based Host Storage

In supported environments and runtimes, configure it using prefixes:

~~~text
AzureWebJobsStorage__accountName=stfunctionshost01
~~~

Or specify service URIs when required (such as sovereign clouds, custom endpoints, or specific features):

~~~text
AzureWebJobsStorage__blobServiceUri=https://stfunctionshost01.blob.core.windows.net/
AzureWebJobsStorage__queueServiceUri=https://stfunctionshost01.queue.core.windows.net/
AzureWebJobsStorage__tableServiceUri=https://stfunctionshost01.table.core.windows.net/
~~~

Verify service URI requirements against your exact Functions host and extensions: not all setups require all three URIs, and `accountName` shorthand has specific applicability rules.

With a supported user-assigned identity:

~~~text
AzureWebJobsStorage__credential=managedidentity
AzureWebJobsStorage__clientId=<UAMI_CLIENT_ID>
~~~

**Switch to identity-based host storage only after verifying compatibility across your hosting plan, worker runtime, extensions, and deployment method.** Other components such as content shares, package deployment, or diagnostic extensions may require separate config and do not automatically inherit host storage token auth.

### 11.3. Host Storage Permissions Differ from Application Permissions

Because the host writes operational state, it typically needs more than Blob Reader. Depending on configuration, it may need Blob/Queue/Table data permissions and certain storage management operations. Exact roles depend on the Functions host, triggers, and extensions.

Example permission breakdown:

| Component | Operation | Governed By |
|---|---|---|
| Functions host | Store locks/receipts/state/leases per feature | Host storage identity and official role matrix |
| `QueueTrigger` | Read/process/delete messages | Binding connection identity |
| Blob input SDK | Read document blobs | App managed identity with Blob Data Reader when sufficient |
| Key Vault reference | Read secrets | Reference identity and vault secret permissions |
| Container Apps/App Service deployment | Deploy artifact | CI/CD identity, distinct from runtime identity |

Never assign Storage Account Contributor or Owner broadly to every Function just because host storage failed startup. First pinpoint the exact missing permissions and narrowest scope.

### 11.4. Migration Plan from Storage Keys to Identity

1. Inventory `AzureWebJobsStorage` and all active connection strings/bindings.
2. Confirm runtime, extension versions, and plan support identity-based connections.
3. Enable managed identity and assign proper data-plane roles first.
4. Prepare a staging environment or test Function App with equivalent host storage.
5. Configure identity-based prefixes cleanly, avoiding exact-match connection string conflicts.
6. Start the Function, inspect host logs, and verify triggers actually fire.
7. Verify networking, private endpoints, DNS, and scaling behavior.
8. Cut over production with a rollback plan; revoke keys only once zero dependencies remain.
9. Document config evidence and rotation plans for any remaining keys.

Pay special attention to **`WEBSITE_CONTENTAZUREFILECONNECTIONSTRING`** and **`WEBSITE_CONTENTSHARE`** on plans using Azure Files content shares. They are not automatically replaced by setting `AzureWebJobsStorage__accountName`; verify identity-based content storage support for your **exact hosting plan**.

## 12. Network Security When Functions Access Key Vault and Storage

### 12.1. Managed Identity Does Not Open Network Paths

A Function with valid RBAC still fails if a firewall or DNS blocks connectivity. Both conditions must hold simultaneously:

~~~text
Function runtime
  ├─ Valid token + RBAC permissions
  └─ Valid DNS + routing + firewall/private endpoint
              |
              v
       Key Vault / Storage / Service Bus
~~~

For production with private networking requirements:

- Determine which outbound VNet integration mode the Function hosting plan supports.
- Configure Private Endpoints on target services for private access.
- Link Private DNS zones, or set up DNS forwarders/Private Resolvers for custom DNS.
- Ensure NSGs, UDRs, and firewalls allow required traffic.
- Verify access to Entra token endpoints and operational runtime dependencies.
- Monitor DNS, connection timeouts, 403s from network rules, and authorization errors separately.

### 12.2. Inbound and Outbound Are Separate

**VNet Integration** for a Function App primarily handles **outbound** traffic from the app into a network per plan capabilities. A **Private Endpoint for a Function App** is a separate inbound feature with its own hosting plan/SKU prerequisites.

Therefore:

- A Function can be publicly reachable over HTTP while reaching Storage over a private network.
- A Function can restrict HTTP inbound while still needing outbound egress to acquire tokens, emit telemetry, or call external APIs.
- Disabling public network access on Storage or Key Vault before Private DNS and routing are ready can sever the Function's connectivity.
- Never equate having a managed identity with restricting the HTTP endpoint to VNet callers.

### 12.3. Why Do Key Vault References Sometimes Fail to Resolve?

Common reasons:

1. System-assigned identity is not enabled or user-assigned identity is not attached.
2. `keyVaultReferenceIdentity` points to the wrong identity.
3. The Vault uses a permission model different from the role you assigned.
4. Role assignment has not propagated yet or lacks permission to read secret values.
5. Wrong secret name/version, or secret is disabled, expired, or deleted.
6. Function App cannot reach the Vault due to firewall, private endpoint, or DNS issues.
7. The platform is still serving an older cached value before its next refresh.

To diagnose, start with **reference resolution status in configuration**, identity/principal, Key Vault permission model, and network reachability. Never log the plaintext secret value to prove it resolved.

## 13. Deployment Slots, Environment Config, and Triggers

### 13.1. A Slot Is Not Automatically a Safe Sandbox

A Function App on a tier supporting deployment slots can run production and staging slots. Depending on the platform, they share certain underlying resources while keeping distinct hostnames and settings.

Some Function triggers **can execute inside the staging slot**, not just after a swap. If staging reads the same Queue Storage or Service Bus subscription as production, both slots will compete for messages, creating side effects or duplicate work.

Designs should:

- Separate queues, topics, and containers per environment when appropriate.
- Verify which settings must be marked as **deployment slot settings** (sticky).
- Control enabling/disabling triggers on staging using supported Functions mechanisms.
- Never put unguarded database migrations or email blasts into startup/warm-up code.
- Check managed identities and Key Vault access per slot as supported.
- Enforce approvals, smoke tests, and rollback plans for both Function App and data.

### 13.2. Sticky Settings Example

~~~text
Production:
  APP_ENV=production              [slot-specific]
  ORDERS_QUEUE_URI=...prod...     [slot-specific]

Staging:
  APP_ENV=staging                 [slot-specific]
  ORDERS_QUEUE_URI=...test...     [slot-specific]
~~~

This illustrates intended isolation, not settings Azure applies automatically. You must explicitly mark settings as sticky on Azure App Service/Function deployment slots. If a connection setting is not sticky, swapping slots can carry unintended values across environments per slot-swap rules.

**Managed identities and slot settings** have specific behaviors; never assume a system-assigned or user-assigned identity automatically swaps with code. Check identity, RBAC, and Key Vault references on both source and target slots before swapping.

### 13.3. Safe Application Configuration Pipeline

A sound release pipeline might look like:

~~~mermaid
flowchart TD
    S["Source code / reviewed IaC"] --> B["Build + tests"]
    B --> A["Immutable artifact"]
    C["Non-secret config in IaC"] --> D["Deploy staging"]
    A --> D
    V["Secrets in Key Vault + RBAC"] -.-> D
    D --> T["Smoke test / verify identity / health"]
    T --> P{"Approval"}
    P -->|Approved| R["Release production"]
    P -->|Rejected| F["Do not shift traffic/triggers"]
    R --> M["Monitor + rollback if needed"]
~~~

If the build artifact includes `host.json` or required `function.json` files, ensure they are packaged for the target worker runtime. Keep secrets out of artifacts; apply configuration per deployment stage.

**Do not grant CI/CD pipelines read access to every Key Vault secret** just to populate app settings. Typically the pipeline only writes the Key Vault reference string while the Function runtime identity holds read permission on the secret.

## 14. Observability, Logging, and Investigating Identity Issues

### 14.1. Distinct Telemetry Sources

| Source | What It Verifies |
|---|---|
| Azure Activity Log | Who enabled identity, edited Function App settings, assigned roles, or changed VNet/resources |
| Microsoft Entra sign-in/managed identity logs (where available) | Identity authentication events within provided log scope |
| Azure Functions host logs | Host startup, trigger initialization, binding errors |
| Application Insights | Exceptions, traces, dependencies, latency, and invocation success |
| Key Vault diagnostic logs | Secret access, denied requests, network/auth evidence per config |
| Azure Storage metrics/logs | Data-plane access, 403/429 errors, availability, throttling |
| Azure RBAC role assignments | Current roles and scopes |
| CI/CD release records | Artifacts, config changes, approvers, timestamps |
| Network/DNS diagnostics | Private endpoint resolution, firewall denies, timeouts |

Do not assume every Function request is fully logged unless Application Insights/diagnostic settings are enabled. Also never assume **Azure Activity Log** records every Blob or Secret read; those live on separate data vs. management planes.

### 14.2. Inspecting App Settings Without Exposing Values

~~~bash
az functionapp config appsettings list \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --query '[].{name:name,slotSetting:slotSetting}' \
  --output table
~~~

When inspecting settings, query only names and metadata rather than values. Never run an unfiltered JSON list command inside pipeline logs where credentials could be printed.

Inspect identity:

~~~bash
az functionapp identity show \
  --resource-group rg-functions-prod \
  --name func-orders-prod \
  --output json
~~~

Check the identity's role assignments against target scopes. When logs lack detail, avoid enabling debug modes that dump all environment variables or authorization headers.

### 14.3. Sample KQL to Find Function Errors

When Azure Functions integrates with workspace-based Application Insights using the `AppExceptions` table:

~~~kusto
AppExceptions
| where TimeGenerated > ago(1h)
| summarize Failures = count() by bin(TimeGenerated, 5m), ProblemId
| order by TimeGenerated asc
~~~

This sample query assumes a schema with `ProblemId`; other workspaces or agents may use different tables or fields. Check actual telemetry schemas and include dimensions separating production/staging and individual Functions.

When investigating Key Vault/Storage errors, inspect HTTP status codes, resource IDs, operations, correlation IDs, and UTC timestamps. **Never save secret values, SAS tokens, or Authorization headers** in investigation logs.

### 14.4. Useful Alerts

- Sudden spike in Function invocation failure rates.
- Host startup or binding initialization errors after switching identities.
- Key Vault access denied or expired secrets.
- Rising Storage authentication/authorization failures.
- Repeated Function restarts following app setting changes.
- Managed identity or role assignment modifications outside approved change windows.
- Secret reference resolution failures or stalled refreshes.
- Growing queue backlogs while triggers appear idle.
- Application Insights telemetry dropping below baseline.
- Unexpected spikes in Key Vault, Storage, Functions, or Log Analytics costs.

Ensure alert payloads never leak secret values or unnecessary sensitive identifiers.

## 15. Common Troubleshooting Workflows

### 15.1. Classifying Error Types

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| App setting missing | Not configured in Azure; confused `local.settings.json` with cloud | Check app setting names and deployment stage |
| Key Vault reference unresolved | Identity, role, vault policy, network, or secret version | Check reference status, principal, RBAC, and DNS |
| Key Vault returns 403 | Missing secret permission, wrong principal, or firewall | Compare permission model and diagnostic logs |
| Storage Blob returns 403 | Missing data role, wrong scope, or Storage firewall | Verify Blob Data Reader/Contributor, endpoint, and network |
| Token acquisition failed | Managed identity not attached, wrong user-assigned client ID, or identity service issue | Inspect identity object, client ID, SDK credential chain |
| Works locally but fails on Azure | Local developer credential holds broader rights than Azure identity | Compare principals/scopes and runtime config |
| Function host fails to start | Broken `AzureWebJobsStorage`, blocked storage, or bad runtime settings | Inspect host logs, host storage URI/roles, and runtime |
| `QueueTrigger` does not run | Wrong connection prefix, extension lacks identity support, or missing Queue Data role | Inspect host/binding logs, service URI, roles, trigger state |
| `BlobTrigger` does not run | Storage extension/mode mismatch or missing host checkpoint/queue permissions | Check extension, container, receipts, and host storage |
| App crashes after config change | Bad setting, unresolved Key Vault reference, startup exception | Check Application Insights and recent version/config changes |
| Vault has private endpoint yet requests time out | Broken VNet integration, DNS, UDR, or NSG | Resolve private FQDN from runtime path; check outbound |
| Connection string still being used | Exact-match setting coexists alongside identity prefix | Inspect all app setting names |
| User-assigned identity has role yet SDK uses system identity | Missing `clientId` or credential chain selects another identity | Check `AZURE_CLIENT_ID` and credential config |
| Function key accepted even though client lacks Entra token | HTTP trigger uses Function key auth | Separate inbound Function auth from outbound managed identity |
| App still uses old secret after rotation | Reference cache, SDK cache, or pinned secret version | Check refresh strategy and versioned reference |
| Pipeline prints secrets | Debug output or unfiltered settings list command | Revoke secret, scrub/restrict logs, fix script |

### 15.2. Ordered Investigation Process

1. **Application:** identify the Function App, slot, subscription, and UTC error timeframe.
2. **Configuration:** check app setting **names**, runtime, extensions, and non-secret values where permitted.
3. **Identity:** confirm which system-assigned or user-assigned identity the host or SDK actually uses.
4. **Permissions:** check data-plane roles and scopes on target resources; never conflate management roles.
5. **Networking:** verify DNS, routes, VNet integration, firewalls, and Private Endpoints.
6. **Secrets/versions:** for vault references, check secret existence, enabled state, and refresh behavior.
7. **Bindings/host:** verify `AzureWebJobsStorage`, host locks/receipts, and extension connection prefixes.
8. **Logs/telemetry:** correlate status codes, correlation IDs, UTC timestamps, and recent changes.
9. **Rollback:** restore prior configuration per plan, verify triggers and data integrity.
10. **Root cause:** log an incident record and add tests or policies to prevent recurrence.

**Never solve 403 errors by granting Resource Group Owner, enabling account keys everywhere, or opening public networking indefinitely.** Fix the exact failing layer.

## 16. Real-World Scenario: Event-Driven Document Processing Function

A team building an invoicing system uses Azure Functions to process newly uploaded files:

- Users upload documents to Azure Blob Storage.
- `BlobTrigger` or Event Grid delivers events into the Function per the chosen architecture.
- The Function reads data, extracts metadata, and sends notifications to a Queue or Service Bus.
- The Function calls a partner API using a token stored in Key Vault.
- Application Insights tracks processing duration and errors.

### 16.1. Configuration Design

| Component | Configuration or Identity | Governance |
|---|---|---|
| Function App | `FUNCTIONS_WORKER_RUNTIME`, `APP_ENV`, telemetry settings | Managed via IaC |
| Host storage | `AzureWebJobsStorage` via supported mechanism | Dedicated identity/roles and networking |
| Blob input | `DOCUMENTS_BLOB_URI` or binding connection prefix | Least-privilege Blob data role |
| Queue output | Supported identity-based connection | Scoped Queue send permissions |
| Key Vault | `PARTNER_API_TOKEN` reference | Secrets User or matching access policy |
| Application code | Azure Identity SDK | Zero hardcoded account keys |
| CI/CD | Deploy artifacts and non-secret config | OIDC/WIF or managed identity; no runtime secret read needed |
| Monitoring | App Insights, host/Storage/Key Vault logs | Never log file payloads or secrets |

### 16.2. Operational Flow

~~~mermaid
flowchart LR
    U["Document upload"] --> B["Azure Blob Storage"]
    B --> F["Processing Azure Function"]
    I["Managed Identity"] -.-> F
    F --> K["Key Vault: partner token"]
    F --> Q["Queue / Service Bus"]
    F --> P["Partner API"]
    F --> M["Application Insights"]
    D["IaC + RBAC + Network"] -.-> F
~~~

Note that with `BlobTrigger`, the Function host needs permissions and networking to watch events, while business logic needs permissions to read the blob via binding or SDK. That distinction affects role assignments and troubleshooting.

### 16.3. Plan for Migrating from Keys to Identity

Suppose v1 uses a Storage connection string with an account key, and v2 migrates to managed identity:

1. Inventory all Function bindings and `AzureWebJobsStorage`.
2. Upgrade/verify extensions support identity-based connections.
3. Enable managed identity and assign roles at the narrowest required scopes.
4. Prepare Storage networking/Private DNS for the runtime environment.
5. Deploy v2 to a test Function App/slot with dedicated queues and containers.
6. Replace connection strings with the corresponding identity-based settings.
7. Verify host startup, `BlobTrigger`/`QueueTrigger`, checkpoints, and live runs.
8. Record image/artifact versions and non-secret setting metadata.
9. Deploy to production with approvals and a monitoring window.
10. Once zero key dependencies remain, rotate/revoke legacy access keys per plan.

If both an exact connection string and identity prefix settings coexist, **verify which configuration the extension actually picks**—never declare migration complete just because a role assignment exists.

### 16.4. Release Acceptance Criteria

- Function receives events accurately without duplicate effects beyond idempotency guarantees.
- Identity reads blobs and writes queues with least-privilege permissions and no overly broad roles.
- App keeps working when legacy keys are revoked in a controlled test.
- Key Vault references resolve properly in the target environment.
- Zero secrets appear in source code, artifacts, logs, or responses.
- Private DNS/networking works without exposing unintended public access.
- On dependency failure, the Function applies proper retries, dead-lettering, and alerts.
- Cost and latency metrics meet agreed SLO thresholds.
- Rollback, rotation, and operational ownership runbooks are ready.

## 17. Performance, Reliability, and Cost

### 17.1. Operational Impact of Managed Identity and Key Vault

Token acquisition, Key Vault resolution, and network calls can affect cold starts or execution time if poorly designed. Key principles:

- Use official Azure Identity SDKs so credential/token caching works out of the box.
- Avoid fetching the same secret from Key Vault on every single invocation without caching or refresh policies.
- Avoid caching secrets indefinitely in global state if rapid rotation is required.
- Set bounded timeouts and retries for Storage, Key Vault, and external APIs.
- Handle 429 throttling, 5xx, and transient network errors differently from 403 permission denied.
- Use async SDKs for I/O-bound workloads when supported by the runtime and implemented cleanly.
- Reuse clients/credentials across worker lifetime when it reduces overhead safely.
- Avoid logging payloads and secrets during retry failures.

**Never retry 403 errors indefinitely:** if a role or policy is wrong, retries only inflate traffic, logs, and cost without fixing the root cause.

### 17.2. Hosting Plans Affect Configuration

Azure Functions supports multiple hosting plans/deployment models, including classic Consumption where supported, Flex Consumption, Premium, and Dedicated. Plans differ in:

- VNet integration and private networking.
- Cold starts, always-ready instances, and scaling.
- Content storage and package deployment models.
- Deployment slots and feature limits.
- Host storage and identity-based auth support.
- Maximum execution duration and concurrency.
- Billing by executions, resource consumption, or provisioned capacity.

Do not apply one rigid `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING`/`WEBSITE_RUN_FROM_PACKAGE` checklist to every plan. Choose the plan first, then verify its supported runtime settings.

### 17.3. Cost Components to Watch

- Function App compute/executions/capacity per plan.
- Host storage and data-plane operations.
- Key Vault secret operations and networking per pricing model.
- Private Endpoints, NAT, VNet integration, or private connectivity components.
- Application Insights/Log Analytics ingestion and retention.
- Data transfer, Service Bus/Queue, Event Grid, and dependencies.
- Staging environments, slot resources, and test workloads.
- Operational effort for rotation, IAM audits, DR, and incident response.

Managed identity eliminates secret management overhead, yet **does not eliminate charges for the services that identity accesses**. Set budget alerts by resource group/tag and review actual Cost Management data.

## 18. Pre-Production Checklist

### Configuration

- [ ] Non-secret config separated from secrets and source code.
- [ ] `local.settings.json` containing secrets is not committed to Git.
- [ ] `FUNCTIONS_WORKER_RUNTIME`, `FUNCTIONS_EXTENSION_VERSION`, and host settings match runtime and plan.
- [ ] Key app settings are managed via IaC or release pipelines.
- [ ] No secret-bearing app setting values printed during CLI checks or logging.
- [ ] Storage and rotation plan exists for third-party secrets.
- [ ] Key Vault references use valid syntax with clear refresh/rotation strategies.
- [ ] Staging and production configs are isolated so triggers never touch the wrong data.

### Identity and Security

- [ ] System-assigned or user-assigned identity selected according to lifecycle needs.
- [ ] Role assignments target the **right principal ID** at minimum scope.
- [ ] Vault permission model and secret-level access verified.
- [ ] Storage data roles match required Blob, Queue, and host operations.
- [ ] Trigger extensions support identity-based connections on the active runtime.
- [ ] Legacy key-based connection strings removed once migration is verified.
- [ ] HTTP Functions enforce independent inbound auth; outbound managed identity does not secure API callers.
- [ ] VNet/private endpoints/DNS and egress verified where services block public access.
- [ ] Zero real credentials inside artifacts, logs, or unprotected pipeline variables.

### Operations

- [ ] Host starts, triggers fire, and bindings work with the new identity.
- [ ] Telemetry tracks 401/403/429 errors, Key Vault failures, and Storage errors.
- [ ] Alerts exist for trigger backlogs, function failures, and secret rotation issues.
- [ ] Runbooks exist for secret rotation, role changes, and network outages.
- [ ] Configuration rollback plan exists if Function startup fails.
- [ ] Periodic audits cover role assignments and Key Vault access logs.
- [ ] Cost tracking covers Functions, Key Vault, Storage, networking, and monitoring.

## 19. Self-Check Questions

1. **How does an app setting differ from a secret?** An app setting delivers configuration values; a secret is a sensitive value needing protection, which may be referenced via a setting.
2. **Does `local.settings.json` automatically apply to a production Function App?** No. Settings must be configured in Azure through your deployment process.
3. **Does `IsEncrypted=false` make `local.settings.json` safe to commit?** No.
4. **What core problem does managed identity solve?** It provides an Azure-managed Entra identity so apps can request tokens without long-lived client secrets.
5. **Does enabling system-assigned identity automatically let a Function read Blobs?** No. You still need data-plane roles and network connectivity.
6. **How do system-assigned and user-assigned identities differ?** One shares its lifecycle with the Function App, while the other is an independent Azure resource.
7. **Can principal ID and client ID be used interchangeably everywhere?** No. Role assignments generally require principal ID; SDKs can use client ID to select a user-assigned identity.
8. **Does using a Key Vault reference require rewriting code that reads environment variables?** Usually no; the platform resolves supported references and the app reads the app setting normally.
9. **Do Key Vault references always refresh instantaneously when a new secret version is created?** No. Account for caching, refresh intervals, and rotation strategies.
10. **Does `Key Vault Reader` allow reading secret values by default?** No. Reading secret payloads depends on the active permission model and specific secret roles/policies.
11. **Can local `DefaultAzureCredential` and production managed identity be two different principals?** Yes; verify RBAC separately for each environment.
12. **Does an HTTP Function with managed identity automatically block unauthorized external callers?** No. Inbound authentication is a separate control.
13. **What is `AzureWebJobsStorage` used for?** Operational connectivity for the Functions host and trigger/host state depending on the plan.
14. **Will replacing the `AzureWebJobsStorage` connection string with `accountName` always work?** No. It requires runtime, plan, and extension compatibility plus proper RBAC.
15. **In `QueueTrigger`, is `connection="OrdersQueue"` a secret?** No. It references a connection setting name or prefix.
16. **Why might a `BlobTrigger` need Queue permissions in addition to Blob permissions?** Certain trigger/host modes use internal queues, receipts, or checkpoints.
17. **Does a Private Endpoint automatically grant permission to read Key Vault?** No. It provides private network routing, not Azure RBAC authorization.
18. **Does a 403 from Storage always mean missing RBAC?** No. It can also result from firewall/network rules or another auth policy; inspect error codes and logs.
19. **Why shouldn't staging and production casually share the same `QueueTrigger` source?** Both slots can compete for messages or trigger unintended side effects.
20. **Why doesn't a deployment pipeline necessarily need permission to read runtime secrets?** The pipeline can write a Key Vault reference while the Function identity reads the secret at runtime.
21. **Should you revert to account keys instead of managed identity simply because an SDK throws 403 on the first try?** No. Inspect the principal, permissions, and network path first.
22. **What must you do if a token is accidentally committed to Git?** Revoke/rotate the token, handle history/exposure assessment, and fix processes to prevent recurrence.
23. **Does managed identity replace Key Vault for third-party API keys?** Not if the third party does not accept Entra tokens; you still need secret management.
24. **What defines a safely configured production Function?** Separated configuration, least-privilege permissions, managed secrets, protected networking, verified triggers, secret-free logs, and rollback/rotation plans.

## 20. References

- [Azure Functions documentation](https://learn.microsoft.com/azure/azure-functions/) — serverless overview, hosting, and managing Function Apps.
- [App settings reference for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-app-settings) — runtime settings and special configuration keys.
- [Develop and test Azure Functions locally](https://learn.microsoft.com/azure/azure-functions/functions-develop-local) — `local.settings.json` and Core Tools.
- [Use managed identities with Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-identity-based-connections-tutorial) — hands-on identity-based access.
- [Identity-based connections in Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference#configure-an-identity-based-connection) — connection setting prefixes and extension compatibility.
- [App Service Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — reference syntax, identity, caching, and networking.
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — system-assigned and user-assigned identities.
- [Azure Key Vault RBAC](https://learn.microsoft.com/azure/key-vault/general/rbac-guide) — roles and permission models.
- [Authenticate Python apps to Azure services](https://learn.microsoft.com/azure/developer/python/sdk/authentication/overview) — Azure Identity and `DefaultAzureCredential`.
- [Azure Storage Blob authorization with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory) — data-plane roles and token authentication.
- [Azure Functions networking options](https://learn.microsoft.com/azure/azure-functions/functions-networking-options) — VNet integration, private endpoints, and plan limits.
- [Azure Functions monitoring](https://learn.microsoft.com/azure/azure-functions/functions-monitoring) — Application Insights and diagnostics.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budget and cost monitoring.

**Conclusion:** A secure Azure Function should not rely on account keys or passwords embedded in source code. Use **app settings for configuration**, **Key Vault for secrets requiring protection**, and **managed identity + Azure RBAC for Entra-enabled services**. Separate caller authentication from outbound permissions, verify host storage and trigger bindings independently, govern networking and Private DNS, and ensure logs never leak credentials. Consider a migration from connection strings to identity complete only when the Function starts cleanly, triggers process live events, and verification and recovery evidence exists on the target hosting plan.

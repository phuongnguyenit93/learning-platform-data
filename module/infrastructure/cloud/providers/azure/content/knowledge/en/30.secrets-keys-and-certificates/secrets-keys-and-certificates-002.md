# Key Vault Authorization with Azure RBAC

A Spring Boot application running on **Azure Container Apps** needs to read a database password from **Azure Key Vault**. Another worker needs to sign data using an asymmetric key without exporting the private key from the vault. Meanwhile, the security team must rotate certificates and monitor access. If **Key Vault Administrator** is assigned to every application to avoid 403 errors, any compromised workload can access unrelated secrets. Conversely, if only **Contributor** is granted on the resource group, the application may **still fail to read secrets** because resource management permissions differ from content access permissions.

**Key Vault authorization with Azure RBAC** means assigning the right **principal**, **role**, and **scope** while controlling the **permission model**, so that a Microsoft Entra ID identity performs only the necessary operations on secrets, keys, and certificates. Access control must be paired with network security, access governance, monitoring, rotation, and verification from the workload's actual identity.

This lesson belongs to the **Secrets, Keys, and Certificates** chapter of the **CLOUD_PROVIDERS_AZURE** module, part of the Microsoft Azure learning path covering subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, data, security, monitoring, and cost control.

> **Scope:** Focuses on **Azure Key Vault** using the **Azure role-based access control (Azure RBAC)** permission model, not Azure Managed HSM. Built-in roles, data actions, APIs/schemas, network behavior, SKUs, limits, and pricing are subject to change; verify current role definitions and Microsoft documentation before applying in production. Examples use placeholders rather than real secret values.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish the **management plane** and **data plane** of Azure Key Vault.
2. Compare **vault access policies** and the **Azure RBAC permission model**.
3. Explain principals, role definitions, role assignments, scopes, inheritance, deny assignments, and PIM.
4. Select appropriate built-in Key Vault roles for reading secrets, managing secrets, crypto operations, and certificates.
5. Grant least-privilege permissions to a system-assigned/user-assigned managed identity or service principal.
6. Inspect role assignments via the Portal, Azure CLI, and IaC examples.
7. Read secrets using the **Azure SDK for Java** without logging secret values.
8. Understand why having the right role can still result in 403 due to firewall/Private Endpoint/DNS.
9. Plan a migration from access policies to RBAC without causing permission outages.
10. Apply logging, Azure Monitor, Azure Policy, PIM, rotation, soft delete, and security reviews.
11. Write a runbook to investigate 401/403/404, propagation delays, secret state, and network errors.
12. Design an architecture separating vaults/identities across dev, staging, prod, and business risk boundaries.

## 2. Scenario: Contributor Still Gets 403

~~~text
Subscription: sub-commerce-prod
Resource group: rg-commerce-prod
Key Vault: kv-commerce-prod
Secret: db-password
App: Spring Boot on Azure Container Apps
Managed identity: mi-commerce-api-prod
~~~

An operator assigns **Contributor** on `rg-commerce-prod`, and the application calls:

~~~java
KeyVaultSecret secret = secretClient.getSecret("db-password");
~~~

The call can fail with **403 Forbidden** if the vault uses the RBAC permission model. Questions to answer:

- Does the principal in the access token match the **object/principal ID** of the running application?
- Does the vault use **Azure RBAC** or **Vault access policy**?
- Does the principal have **Key Vault Secrets User**, or a role with the data action to read secret values, at a valid scope?
- Is an assignment from a parent scope, group, or PIM having an effect?
- Is the vault firewall or private networking blocking the path?
- Does the secret exist, is it enabled, is the version valid, and is the app using the right URI?
- Has the newly granted permission propagated to the data plane yet?

**Do not fix the error by granting Owner/Administrator across the subscription.** First identify the exact failing stage, then grant the minimum required permission.

## 3. Secrets, Keys, and Certificates Differ

| Object | Nature | Example operations |
|---|---|---|
| **Secret** | Secret value stored and returned when a principal is authorized | Get, set, list metadata, delete, recover |
| **Key** | Cryptographic key material and policy; private key export may be disallowed | Sign, verify, wrap/unwrap, encrypt/decrypt, rotate |
| **Certificate** | Certificate and issuance/renewal lifecycle; may have backing key/secret | Create/import, get, list, renew, retrieve content |
| **Vault** | Resource boundary containing objects, networking, IAM, diagnostics | Configure settings, permission model, policies |

### Secret

A secret such as `db-password` can have **multiple versions**. Apps read the latest or a specific version depending on SDK/API usage. RBAC governs whether an identity can read the object; it **does not automatically rotate the database password** when the secret changes.

### Key

With a Key Vault crypto key, an app typically invokes cryptographic operations inside Key Vault **without receiving the private key material**. **Key Vault Crypto User** permissions differ from key management permissions in **Crypto Officer**.

### Certificate

A Key Vault certificate can be linked to a **backing secret** and key. Reading metadata/public certificates, using the private key, or exporting certificate content each have distinct permission requirements. Do not assume that certificate metadata read access automatically allows retrieving the private key, and do not grant full secret permissions just because a consumer needs the public certificate.

## 4. Two Permission Models of Key Vault

A Key Vault can be configured with either **Vault access policy** or **Azure role-based access control** for **data-plane** authorization.

| Aspect | Access policy mode | Azure RBAC mode |
|---|---|---|
| Data-plane permission source | Access policies on the vault | Role assignments containing data actions |
| Granting permissions | Secret/key/cert permissions per access policy | Built-in/custom roles and scopes |
| Inheritance from subscription/RG | Does not follow Azure RBAC role assignment hierarchy | Can inherit from parent scopes |
| Permission governance | Editing access policies on the vault | Azure authorization role assignment management |
| Auditing | Vault configuration and audit logs | ARM Activity Log, IAM/PIM, and data-plane audit |
| Governance | Must restrict who can edit access policies | Supports role scope, PIM, policy, and assignment conditions |

**Strict rule:** When a vault enables **Azure RBAC authorization**, **legacy access policies no longer grant data-plane access**. Permissions from access policies and RBAC do not stack. Conversely, in access policy mode, assigning Key Vault Secrets User via RBAC **is not sufficient** to replace an active data-plane access policy.

Changing the permission model on a live vault can break applications, cert automation, backup/restore, or rotation. Always build an inventory, map roles, and prepare testing before cutover.

## 5. Management Plane vs. Data Plane

~~~mermaid
flowchart LR
  ADMIN["Infra admin / Azure CLI"] --> ARM["Azure Resource Manager"]
  ARM -->|"Management RBAC actions"| CONFIG["Vault configuration, role assignments"]
  APP["App managed identity"] -->|"Entra access token"| ENDPOINT["Key Vault data endpoint"]
  ENDPOINT -->|"Data-plane RBAC dataActions"| OBJECTS["Secrets / Keys / Certificates"]
  CONFIG -.->|"Does not inherently read values"| OBJECTS
~~~

### Management Plane

Operations through ARM:

- Create, view, update, or delete a Key Vault resource.
- Configure networking/firewall, tags, permission model, diagnostics.
- Manage role assignments when a principal has `Microsoft.Authorization/roleAssignments/write` and satisfies policies/conditions.

Roles like **Contributor**, **Owner**, **User Access Administrator**, or **Role Based Access Control Administrator** primarily concern the management plane and IAM control. **Key Vault Contributor** manages the Key Vault resource but **does not inherently grant reading secret values in RBAC mode**.

### Data Plane

Requests to endpoints:

~~~text
https://<VAULT>.vault.azure.net/secrets/...
https://<VAULT>.vault.azure.net/keys/...
https://<VAULT>.vault.azure.net/certificates/...
~~~

Examples: `get secret value`, `set secret`, `sign`, `decrypt`, `get certificate`. These permissions come from role **dataActions** when the vault uses RBAC.

### One Person Can Hold Both Types of Permissions

A platform engineer might legitimately manage vault configuration and be authorized to view secrets under a defined process, but those should be **two deliberate authorization decisions**, not one unconditional broad privilege.

## 6. Azure RBAC Components

| Component | Meaning |
|---|---|
| **Principal** | User, group, service principal, or managed identity recognized by Entra |
| **Role definition** | Set of `actions`/`notActions`, `dataActions`/`notDataActions` |
| **Role assignment** | Binds a principal and role at a scope |
| **Scope** | Subscription, resource group, vault, or supported child object |
| **Inheritance** | Assignments at parent scopes can apply to child scopes |
| **Deny assignment** | Explicit deny mechanism that can affect effective access |
| **Role assignment condition** | Constrains which roles can be assigned/revoked in supported cases |
| **PIM** | Manages eligible/time-bound activations with approval where supported |

Roles are **assigned by principal ID**, not “any app with a similar name”. A standard assignment looks like:

~~~text
Principal: mi-commerce-api-prod (principal object ID)
Role: Key Vault Secrets User
Scope:
  /subscriptions/<SUB_ID>/resourceGroups/rg-commerce-prod/
  providers/Microsoft.KeyVault/vaults/kv-commerce-prod
~~~

## 7. Scope and Inheritance: Permissions Can Be Broader Than You Think

~~~mermaid
flowchart TD
  SUB["Subscription"] --> RG["Resource group"]
  RG --> KV1["kv-commerce-prod"]
  RG --> KV2["kv-reports-prod"]
  KV1 --> SEC1["db-password"]
  KV1 --> SEC2["payment-provider-token"]
  SUB -.->|"Role assignments inherited"| KV1
  RG -.->|"Role assignments inherited"| KV2
~~~

If an operator is granted Key Vault Administrator at the **subscription** level, they may gain data-plane privileges across many vaults in that subscription when those vaults use RBAC. Likewise, an assignment on a **resource group** can affect all child vaults.

### Scope Selection Guidelines

- **Vault scope** is a good starting point for an application authorized on secrets within a single vault.
- **Subscription/RG scope** only when clearly justified and policy-approved; must account for existing and future vaults.
- **Object-level scope** for a secret/key/certificate may be supported, but increases management overhead; consider separate vaults when apps/tenants need clear isolation.
- Check inherited assignments, group memberships, PIM activations, and role definitions.
- For multi-tenant business data, **Key Vault vault boundaries do not replace application-level tenant ownership logic**.

## 8. Built-In Key Vault Roles to Know

| Role | Suitable task | Important limitation |
|---|---|---|
| **Key Vault Reader** | Read vault/object metadata per defined permissions | Does not allow reading secret values on its own |
| **Key Vault Secrets User** | Read secret values | Does not grant modifying/deleting secrets |
| **Key Vault Secrets Officer** | Manage secrets and secret data-plane operations | Does not assign Azure RBAC roles |
| **Key Vault Crypto User** | Perform permitted cryptographic operations on keys | Does not inherently create/delete keys |
| **Key Vault Crypto Officer** | Manage keys and crypto activities per role | Does not inherently manage role assignments |
| **Key Vault Certificate User** | Access certificate contents per role definitions | Does not inherently read all other secrets |
| **Key Vault Certificates Officer** | Administer certificate lifecycle | Not a subscription Owner |
| **Key Vault Administrator** | Very broad data-plane permissions across keys/secrets/certificates | Not equivalent to management-plane Owner |
| **Key Vault Contributor** | Manage vault resource/control plane | Does not read secret values in RBAC mode |
| **Key Vault Data Access Administrator** | Manage assignments for a subset of Key Vault data roles with built-in conditions | Not an unconstrained Owner |
| **Key Vault Purge Operator** | Specialized purge operations where supported | Does not replace Data Administrator or Reader |

**Note:** This is a role selection guide and **does not substitute for inspecting actual `actions` and `dataActions`**. Especially for certificate backing secrets, crypto algorithms, listing metadata, purge, and rotation operations, inspect the exact role definition version and test the actual API.

### Choose the Right Role by Need

~~~text
API app only gets DB password:     Key Vault Secrets User
Automation needs set/rotate:       Key Vault Secrets Officer
App signs invoices:                Key Vault Crypto User
Key management team:               Key Vault Crypto Officer
Certificate operator:              Key Vault Certificates Officer
Metadata-only auditor:             Key Vault Reader
Human emergency data access:       Key Vault Administrator + PIM, narrow scope
~~~

Never use **Key Vault Administrator** as a quick fix for every application 403 error.

## 9. Who Can Assign Roles?

**Having permission to read secrets** is different from **having permission to grant others access to read secrets**.

The principal creating a role assignment must hold the corresponding Azure management authorization, such as:

- **Owner** or **User Access Administrator** per scope/policy.
- **Role Based Access Control Administrator** per actual conditions/constraints.
- **Key Vault Data Access Administrator** supports a specific set of Key Vault roles with role assignment conditions, not arbitrary Azure role assignments.

**Key Vault Secrets Officer/Administrator** are primarily data-plane roles and do not automatically allow adding IAM role assignments.

### Privilege Escalation Path to Block

Someone with permission to update vault configuration—especially the **permission model**—could attempt to switch back to access policy mode and grant themselves access policy permissions if guardrails allow it. Use **Azure Policy**, change management, IaC reviews, and tight control over who holds `Microsoft.KeyVault/vaults/write` to prevent bypassing RBAC governance.

## 10. Identity: Client ID vs. Principal ID

| Value | Nature | Used for |
|---|---|---|
| **Tenant ID** | Directory containing identities | Identifying tenant/issuer |
| **Application/client ID** | App/managed identity client ID | Client configuration; selecting UAMI when needed by SDK |
| **Principal/object ID** | Security principal ID in the tenant | **Assigning roles via `--assignee-object-id`** |
| **Vault ARM ID** | Vault resource ID | Role assignment scope |
| **Vault URI** | HTTPS data-plane endpoint | SDK SecretClient/CryptographyClient |

Example user-assigned managed identity (UAMI):

~~~text
name: mi-commerce-api-lab (example: mi-commerce-api-prod)
clientId:    <CLIENT_GUID>
principalId: <PRINCIPAL_OBJECT_GUID>

RBAC assignment uses: principalId
Java/Azure Identity UAMI selection uses: clientId
~~~

Oops—let's keep line 239 exact: `name: mi-commerce-api-prod`. Let's make sure we don't alter `mi-commerce-api-prod`! Good catch while thinking—we will write `name: mi-commerce-api-prod` verbatim.

Do not swap these two GUIDs. When a **system-assigned identity** is deleted along with its compute resource and the compute resource is recreated, the `principalId` can change. Old role assignments may point to an orphaned principal; new deployments must reconcile and grant permissions to the new `principalId`.

## 11. Request Path for Reading a Secret

~~~mermaid
sequenceDiagram
  participant A as Java app
  participant E as Microsoft Entra ID
  participant V as Key Vault
  A->>E: Acquire access token using managed identity
  E-->>A: Token for Key Vault resource
  A->>V: GET /secrets/db-password + Bearer
  V->>V: Check token, vault permission model, networking
  V->>V: Evaluate RBAC dataActions + scope + principal
  alt authorized
    V-->>A: Secret value + metadata
  else not authorized
    V-->>A: 403 + diagnostic error
  end
~~~

This diagram is a logical model and does not imply the service calls Azure Resource Manager on **every** request. Actual permissions involve caching/propagation.

### Distinguish Two Error Layers

- **Azure Identity token acquisition failure:** SDK failed to obtain an access token due to unavailable runtime identity, credential chain, tenant mismatch, or network path to the authority.
- **Key Vault 403:** API processed the request but denied it due to authorization, permission model, network policy, or object operation.

A successful token acquisition by `DefaultAzureCredential` **does not prove** the principal holds `Key Vault Secrets User`.

## 12. Creating an RBAC Vault via Azure Portal

1. Verify the **subscription/resource group** and tenant for the lab.
2. Create a **Key Vault** with a valid name and appropriate region.
3. Under **Access configuration / Permission model**, select **Azure role-based access control**.
4. Verify soft delete/purge protection/retention per policy.
5. Choose firewall/public network access/Private Endpoint appropriately; do not open public access for production just to test.
6. Create the vault, and record the **Vault URI** and **ARM resource ID**.
7. Open **Access control (IAM)** and inspect existing/inherited role assignments.
8. **Add role assignment** for the app identity, selecting **Key Vault Secrets User** at vault scope.
9. Assign separate roles for rotation/certificate/security admins.
10. Wait for propagation and test the actual API from the workload's real identity and network.

Successfully creating a vault does not automatically grant the creator permission to read all secret values. If the Portal shows metadata but not values, first check the data-plane role of the signed-in principal.

## 13. Azure CLI: Reading Vault Configuration

Bash example in Azure Cloud Shell/Linux terminal logged in via an approved process:

~~~bash
az account show \
  --query "{subscription:name,subscriptionId:id,tenantId:tenantId}" \
  -o json

RG="rg-commerce-lab"
KV="kv-commerce-lab"

az keyvault show \
  --resource-group "$RG" \
  --name "$KV" \
  --query "{id:id,name:name,rbac:properties.enableRbacAuthorization,network:properties.publicNetworkAccess}" \
  -o json
~~~

Depending on CLI version, the returned schema may differ or properties may be flattened. If `rbac` displays `null`, inspect the actual response/Portal; **do not conclude RBAC is off just because a JMESPath query is misaligned**.

Get the vault ARM scope:

~~~bash
KV_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$KV" \
  --query id -o tsv)

echo "$KV_ID"
~~~

Format:

~~~text
/subscriptions/<SUB_ID>/resourceGroups/rg-commerce-lab/providers/Microsoft.KeyVault/vaults/kv-commerce-lab
~~~

## 14. CLI: Inspecting Role Definitions and Inherited Assignments

~~~bash
az role definition list \
  --name "Key Vault Secrets User" \
  --query "[].{name:roleName,id:id,permissions:permissions}" \
  -o json

az role definition list \
  --name "Key Vault Contributor" \
  --query "[].{name:roleName,id:id,permissions:permissions}" \
  -o json
~~~

Distinguish `actions`/`notActions` for the management plane from `dataActions`/`notDataActions` for the data plane. A role named “Contributor” is not proof of having the `getSecret` data action.

List role assignments:

~~~bash
az role assignment list \
  --scope "$KV_ID" \
  --include-inherited \
  -o table
~~~

`--include-inherited` reveals permissions from the subscription/RG. With group assignments, PIM, deny assignments, or CLI principal lookup restrictions, inspect **effective access** and tenant identities using appropriate IAM tools rather than relying solely on display names.

## 15. Assigning Key Vault Secrets User to the Right Principal and Scope

This example **modifies actual permissions**; run only in a lab vault or under change approval:

~~~bash
RG="rg-commerce-lab"
KV="kv-commerce-lab"

KV_ID=$(az keyvault show \
  --resource-group "$RG" --name "$KV" \
  --query id -o tsv)

PRINCIPAL_OBJECT_ID="<MANAGED_IDENTITY_PRINCIPAL_ID>"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID"
~~~

`--assignee-object-id` is the **object/principal ID**, **not the client ID**. `ServicePrincipal` is right for service principal/managed identity types; use the actual principal type for users/groups. `--scope` targets only the vault, not the entire subscription.

### Common Errors

- Caller lacks `Microsoft.Authorization/roleAssignments/write` at that scope.
- Vault is still in **access policy mode**.
- `principalId` was copied from a different UAMI than the one the app uses.
- Assignment exists but has not propagated yet.
- Role assigned on a different vault, or a parent scope has a deny/conditional constraint.
- IAM role is right, but network/firewall still blocks the workload from reaching the vault.

**Do not run role assignment creation repeatedly to “wait out a 403”.** First verify the assignment ID and the actual caller principal.

## 16. User-Assigned Identity: Retrieving clientId and principalId

~~~bash
UAMI_RG="rg-identities-lab"
UAMI_NAME="mi-commerce-api-lab"

az identity show \
  --resource-group "$UAMI_RG" \
  --name "$UAMI_NAME" \
  --query "{principalId:principalId,clientId:clientId,id:id}" \
  -o json

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$UAMI_RG" --name "$UAMI_NAME" \
  --query principalId -o tsv)

az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID"
~~~

If an Azure app has multiple user-assigned identities attached, the SDK may require `clientId`/the `AZURE_CLIENT_ID` environment variable to pick the right identity. **Role assignments use `principalId`**, whereas runtime identity selection configuration typically uses **`clientId`**.

### System-Assigned Identity

For a system-assigned identity, retrieve the principal ID from the active Azure compute resource itself; if a VM/Container App is recreated, inspect the new identity instead of trusting an old assignment by resource name.

## 17. Java SDK: Accessing Secrets with DefaultAzureCredential

In a Spring Boot/Java module, use the Azure SDK for Java with these dependencies:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-sdk-bom</artifactId>
      <version>${azure.sdk.bom.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
  </dependency>
</dependencies>
~~~

This is a POM fragment; `azure.sdk.bom.version` must be declared by the project with a verified version, not a guessed value.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class VaultReader {
    private final SecretClient client;

    public VaultReader(String vaultUrl) {
        this.client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }

    public boolean canGetDemoSecret() {
        KeyVaultSecret item = client.getSecret("demo-config");
        // NEVER write item.getValue() to logs.
        return item != null;
    }
}
~~~

**Technical note:** `getSecret` fetches the secret **value into process memory** even if the method only returns a boolean. It is a real **data-plane get** test, not a metadata-only probe. Use only a non-sensitive lab secret for testing; in production, read only for required business logic and protect the value in memory. If you only want metadata, use appropriate metadata-reading APIs/roles.

### Identity When Running Locally vs. on Azure

- **Local:** `DefaultAzureCredential` can obtain tokens from developer tooling via the supported chain.
- **Azure:** it can obtain tokens from a system-assigned/user-assigned managed identity or workload identity per configuration.
- Both environments can call the exact same `getSecret` using **two different principals** → one succeeds while the other gets 403.

## 18. Spring Boot: SecretClient Singleton and Configuration

Avoid creating a new credential/client per HTTP request or calling directly from arbitrary business code.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VaultConfiguration {

    @Bean
    public SecretClient secretClient(
            @Value("${app.key-vault.url}") String vaultUrl) {
        return new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

Externalized configuration:

~~~yaml
app:
  key-vault:
    url: ${AZURE_KEYVAULT_URL}
~~~

Example URL:

~~~text
AZURE_KEYVAULT_URL=https://kv-commerce-lab.vault.azure.net/
AZURE_CLIENT_ID=<USER_ASSIGNED_IDENTITY_CLIENT_ID_IF_REQUIRED>
~~~

Do not log secret values/access tokens, do not commit client secrets, and separate runtime **Secrets User** permissions from rotation **Secrets Officer** permissions. In production, plan caching/refresh/rotation: reading Key Vault on every request increases latency, operation cost, and throttling risk; however, caching for too long prevents a new password from taking effect. There is no universal cache TTL that fits every workload.

If using Spring Cloud Azure Key Vault configuration integration, verify exact versions, precedence, and refresh semantics; this `SecretClient` example **does not automatically enable Spring property sources**.

## 19. Key Vault Crypto User: Signing and Encrypting Without Exporting the Private Key

An invoicing service needs to generate digital signatures for invoices without managing keys. The design should be:

~~~text
Workload: mi-invoice-signer-prod
Vault: kv-signing-prod
Key: invoice-signing-key
Required actions: sign/verify per supported algorithm and key version
Role candidate: Key Vault Crypto User
Unneeded actions: create/delete keys, get secrets, assign IAM roles
~~~

### Distinguish Key Usage from Key Administration

- **Key Vault Crypto User** is suitable when an application performs **cryptographic operations** permitted by the role/key policy.
- **Key Vault Crypto Officer** is for identities administering keys per defined permissions, not the default role for an app that only signs.
- **Key Vault Administrator** is too broad for an ordinary signing workload.
- **Key Vault Reader** can view metadata without signing/decrypting under that role.

A `CryptographyClient` can call `sign`, `verify`, `encrypt`, `decrypt`, `wrapKey`, or `unwrapKey` depending on key type, algorithm, and permitted key operations. **Not every key permits every algorithm**, and not all key material is exportable.

### Key Version and Rotation

A key identifier can include a version:

~~~text
https://kv-signing-prod.vault.azure.net/keys/invoice-signing-key/<VERSION>
~~~

If signed data requires long-term auditing, store the version/algorithm needed to verify signatures after key rotation. Choosing “latest key” vs. pinning a version must follow business protocol requirements rather than an unexamined default. For CMK on Azure services, service-specific roles/permissions may apply alongside Crypto User; **do not assign broad roles simply because encryption is involved**.

## 20. Certificate Lifecycle and Commonly Confused Permissions

A certificate in Key Vault can link to a certificate object, a key, and a **backing secret**. Different needs require different checks:

| Need | Permission to evaluate |
|---|---|
| View metadata: subject, expiry, issuer | Role with metadata permissions |
| Read certificate contents/public certificate | **Key Vault Certificate User** where appropriate |
| Create/import/renew certificate | **Key Vault Certificates Officer** per role definitions |
| Read private-key-containing PFX via backing secret | Verify exact certificate/secret data actions and exportability |
| Use key to sign/decrypt without export | Crypto role and corresponding key operation |
| Add another certificate consumer | Role-assignment management, not just Certificate Officer |

**Do not conclude Certificates User can read arbitrary secrets across the vault.** Conversely, do not assume a certificate consumer only needs metadata if TLS deployment requires the private key via service integration.

### Common Certificate Errors

- Certificate expired because automation failed to renew.
- Key/certificate disabled.
- Private key export disallowed by policy.
- Consumer service has not refreshed the new version.
- Missing permission to read the required backing object.
- Vault private endpoint unreachable from App Service/Application Gateway.
- Consumer's identity does not match the identity assigned the role.

**RBAC does not automatically renew certificates.** You still need owner management, expiry alerts, renewal jobs, consumer reloads, and rollback plans.

## 21. Network Security Is an Independent Layer from Azure RBAC

~~~mermaid
flowchart LR
  APP["App / Managed identity"] --> AUTH["Entra token"]
  AUTH --> NET{"Key Vault DNS, route, and firewall?"}
  NET -->|Blocked| NERR["Network denied / timeout / firewall 403"]
  NET -->|Allowed| VAULT["Key Vault data plane"]
  VAULT --> RBAC{"DataActions + scope for principal?"}
  RBAC -->|No| F403["Authorization 403"]
  RBAC -->|Yes| OK["Get secret / crypto / certificate"]
~~~

The **Key Vault Secrets User** role does not create a VPN, VNet peering, or Private Endpoint. Conversely, a **Private Endpoint** does not grant permission to read secrets.

Verify in order:

1. Does the app resolve the **vault FQDN** properly; does private DNS return the private IP when using a Private Endpoint?
2. Do routes/NSGs/firewalls/egress allow HTTPS connectivity to the vault?
3. Is the Private Endpoint connection Approved and targeting the right subresource?
4. Are the vault's public network access/firewall settings aligned with policy?
5. Does the workload have egress to the required Entra ID authentication endpoints?
6. Are the TLS trust store, proxy, and DNS forwarder/Private Resolver functioning?
7. Only then inspect **principal + RBAC role + permission model**.

### Trusted Microsoft Services Is Not Allow-All

Enabling **trusted services** applies only to an Azure-designated set of services and operations; it does not mean every Azure service and every tenant bypasses the firewall. Data-plane RBAC must still be valid.

### On-Premises and Private Routing

If a Java app runs on-premises and the vault only exposes a Private Endpoint in an Azure VNet, you need **VPN/ExpressRoute or an allowed network**, private DNS forwarding, and routing. Knowing the vault URI does not guarantee network reachability.

## 22. Replacing Access Policies with Azure RBAC: Migration Plan

Switching the permission model on a live vault can cut off every app's access. Never start with an `az keyvault update` command without preparation.

### Safe Process

1. **Inventory:** list vaults, access policies, identities, and consumers.
2. **Operations mapping:** document get/list/set/delete secrets, sign/decrypt keys, get/renew certificates, backup/restore, and rotation.
3. **Scope review:** inspect permissions inherited from subscription/RG that could widen once RBAC takes effect.
4. **Roles design:** map to minimal built-in/custom roles, separating reader, writer, and operator.
5. **Pre-assign:** create Azure RBAC assignments for principals using exact object IDs and wait for propagation.
6. **Lab/pilot test:** test on an equivalent RBAC vault using real runtime identities and networking.
7. **Change window:** agree on cutover timing, SLA, stakeholders, rollback, and backup/recovery plan per policy.
8. **Switch mode:** switch the vault to Azure RBAC after approval.
9. **Smoke test:** test get/rotate/sign/certificate operations with the actual identities.
10. **Observe:** monitor 401/403/5xx, secret refresh, cert bindings, and applications.
11. **Remediate:** fix missing roles/scopes precisely; never grant subscription Owner.
12. **Policy guardrail:** enforce Azure RBAC mode via Azure Policy where appropriate to prevent drift back to access policy mode.
13. **Audit:** retain change tickets, role assignment IDs, and test evidence.

### Why Pre-Assigning Roles Before Switching Is Not Full Proof

While the vault is still in **access policy mode**, data-plane RBAC assignments can exist without being evaluated to authorize operations. Therefore, you must test **after cutover** or on a matching pilot vault—never conclude “role assignments exist, so migration is guaranteed safe”.

### Model Switch Command — Only When Approved

~~~bash
# HIGH IMPACT: use only per change plan on an authorized vault.
az keyvault update \
  --resource-group "$RG" \
  --name "$KV" \
  --enable-rbac-authorization true
~~~

**Consequence:** Legacy access policies are no longer the data-plane authorization source in RBAC mode. Any overlooked rotator, backup automation, or certificate consumer will hit 403 immediately upon cutover. Record the prior state, maintain a rollback plan, and check guardrails that restrict switching back.

## 23. Azure Policy: Locking Down Permission Model Governance

Even if a principal lacks Secrets User, an administrator who can modify vault configuration could change the **permission model** and create a self-escalation path via access policies in some scenarios. Therefore, add governance controls:

- Policy requiring vaults to use **Azure RBAC** per organizational standards.
- Policy restricting public network access or requiring private endpoints for sensitive vaults.
- Policy enforcing purge protection/retention per compliance requirements.
- Restrict `Microsoft.KeyVault/vaults/write` and principals allowed to modify RBAC assignments.
- Manage role assignments through IaC/code review, PIM, and approval.
- Alert on changes to permission model, network rules, or broad role assignments.
- Audit role assignments at subscription/RG levels to catch overly broad inheritance.
- Separate subscriptions or resource groups when strict environment boundaries are needed.

**An Azure Policy deny can block changes even for a caller with Owner.** Do not disable policy at a parent scope just to make a lab work.

## 24. PIM, Just-in-Time Access, and Human Administrators

Use **Microsoft Entra Privileged Identity Management (PIM)** for high-privilege roles where supported/licensed:

~~~text
Developer:
  Lab Secrets User -> required permissions, narrow scope

On-call:
  Eligible Key Vault Administrator -> specific production vault
  Activate -> MFA + justification + approval, limited duration

Security/IAM:
  Data Access Administrator or appropriate role-assignment management role
  Scope -> vault, with reviews

Application:
  Managed Identity + Secrets User/Crypto User
  No permission to grant IAM roles
~~~

PIM reduces **standing** privileges, but it cannot rescue an **overly broad** role once activated. Require **narrow scopes, short durations, approvals, auditing, and periodic access reviews**. Some PIM features depend on entitlement/licensing and are not available in every tenant by default.

### Break-Glass

Emergency access accounts need:

1. Strict protection, designated owners, and an emergency access procedure.
2. Never used for routine secret reads.
3. Break-glass event monitoring and post-incident review.
4. Policy-compliant role/scope/duration.
5. An independent verification path for network/data-plane access if Key Vault is impacted.
6. Regular drills within approved scope.

Never use a script that grants Owner to everyone as a “break-glass runbook”.

## 25. Soft Delete, Purge Protection, and RBAC

**Soft delete** enables recovery of deleted vaults/objects within the retention period. **Purge protection** prevents permanent deletion before retention expires per service semantics. However:

- It is not a **full backup system** replacing recovery planning.
- RBAC governs delete/recover/purge operations per role/permission model.
- Destructive privileges must be tightly scoped and separately audited.
- An app that only reads secrets **does not need delete or purge**.
- Specialized purge permissions should not be granted to daily operators without approval.
- Retention and purge-protection settings must meet compliance rules, especially when resources hold keys encrypting other data.

### Tough Edge Case

If a key used as a CMK for storage/databases is deleted/purged, that data can become **unreadable** even though the storage resource itself still exists. When scheduling key rotation/deletion, inventory dependent resources, backup/restore strategies, and recovery feasibility.

## 26. Secret Rotation: Separating Reader and Writer

~~~mermaid
flowchart LR
  ROT["Rotation job: Secrets Officer"] --> VAULT["Key Vault"]
  APP["App: Secrets User"] --> VAULT
  ROT --> BACK["Database / external service credential"]
  BACK --> VERIFY["Validate new credential"]
  VERIFY --> RELEASE["Deploy/refresh app secret version"]
  RELEASE --> MON["Monitor / rollback"]
~~~

RBAC lets an application read and automation write secrets; it **does not automatically sync the password inside the database**. If the database changes its password before the app refreshes, the app can go down. If Key Vault changes the secret before the target service changes its password, authentication will also fail.

### Controlled Rotation Procedure

1. Create a new credential at the target service using dual-credential/overlap capability.
2. Set the **new secret version** using the rotation identity.
3. Test the new credential without logging plaintext.
4. Deploy/reload the application to pick up the new secret per maintenance/rollout policy.
5. Watch error rates, connection pools, and downstream 401/403s.
6. Revoke the old credential once no consumers depend on it.
7. Maintain a rollback/compensation plan if rotation fails.
8. Audit actor/time/version without storing raw values.

Grant only **Key Vault Secrets User** to the reading runtime. Rotation automation can use **Secrets Officer** at the appropriate scope. If the rotation job also modifies credentials in Azure SQL/an external database, permissions on that system are **separate** from Key Vault RBAC.

## 27. 403: Classify Before Changing Permissions

~~~mermaid
flowchart TD
  E["Java SecretClient: failure"] --> STATUS{"HTTP response present?"}
  STATUS -->|No| NET["Network, DNS, proxy, TLS, auth endpoint"]
  STATUS -->|Yes| CODE{"HTTP status / error code?"}
  CODE -->|401| ID["Token/credential/audience/tenant"]
  CODE -->|403 firewall| FIRE["Vault firewall/private endpoint"]
  CODE -->|403 authorization| MODE{"Vault RBAC mode?"}
  MODE -->|No| POLICY["Access policies"]
  MODE -->|Yes| ROLE["Object ID, role dataActions, scope, inheritance, propagation"]
  CODE -->|404| OBJ["Secret name/version/existence/visibility"]
  CODE -->|429/503| RETRY["Backoff/jitter/retry budget"]
~~~

### Troubleshooting Matrix

| Symptom | Likely cause | What to check |
|---|---|---|
| Contributor gets `getSecret` 403 | Management role lacks dataActions | Secrets User at vault scope |
| Secrets User, vault in access policy mode | Wrong permission model | Access configuration |
| Role assigned to UAMI clientId | Wrong ID | Must use principalId |
| App works locally, Azure gets 403 | Different credentials/identities | Runtime managed identity |
| Newly assigned role still returns 403 | Propagation/group/token cache | Verify assignment, bounded wait |
| 403 from firewall | Network not allowed | Private DNS/firewall/route |
| Read role gets `setSecret` 403 | Role lacks write data action | Rotation identity + Secrets Officer |
| Metadata list OK, value get 403 | Metadata role differs from value role | Role definitions and actual API |
| Key sign 403 | Crypto role/algorithm/key state | Key Vault Crypto User/operations |
| Cert public OK, private export fails | Certificate/backing secret/export policy | Exact API/role/cert properties |
| Role assignment create 403 | Caller lacks ARM IAM write | Owner/UAA/KV Data Access Admin per policy |
| Vault 404 | Wrong/missing resource/secret/version name | Vault URL, object state |
| 429/503 | Throttling/transient failure | SDK retry, metrics, backoff |
| Connection timeout | DNS/VNet/Private Endpoint | Test from the actual host |
| Access token acquisition fails | Managed identity unavailable | SDK credential chain, env |

**Service error codes vary by API/version**; you may see codes like `ForbiddenByRbac`, `ForbiddenByFirewall`, or other messages. Rely on **HTTP status, actual error code, and correlation ID** rather than hardcoding a single error string.

## 28. Java SDK: Safe Error Handling

~~~java
import com.azure.core.exception.HttpResponseException;
import com.azure.security.keyvault.secrets.SecretClient;

public final class KeyVaultAccessProbe {
    private final SecretClient client;

    public KeyVaultAccessProbe(SecretClient client) {
        this.client = client;
    }

    public boolean canGetLabSecret(String name) {
        try {
            var item = client.getSecret(name);
            // Never print item.getValue(), tokens, headers, or raw response bodies.
            return item != null;
        } catch (HttpResponseException ex) {
            int status = ex.getResponse() == null
                ? -1 : ex.getResponse().getStatusCode();
            System.err.println("Key Vault request failed status=" + status);
            throw ex;
        }
    }
}
~~~

`getSecret` is an actual request that reads the secret value, so only use a **non-sensitive lab secret** for testing. Production logs should record a **redacted structured error category, requestId, operation, and safe principal metadata**; never assume every exception message is safe to expose.

### Distinguish Retries from Fixing Permissions

- **401/403** from misconfigured identity/role/network: endless retries will not fix it.
- Role just assigned: bounded retesting makes sense for propagation, but verify principal/scope first.
- **429/503**: SDK retry/backoff with a budget, respecting service hints.
- Timeout: diagnose DNS, proxy, TLS, Private Endpoint; never grant extra Owner permissions.

## 29. Inspecting Role Assignments and Data-Plane Testing

**Role inspection** cannot replace **testing the actual API**.

~~~bash
az role assignment list \
  --scope "$KV_ID" \
  --include-inherited \
  --query "[].{principal:principalId,role:roleDefinitionName,scope:scope}" \
  -o table
~~~

When using a lab test secret, you can test data-plane `get` without printing the value:

~~~bash
az keyvault secret show \
  --vault-name "$KV" \
  --name "demo-config" \
  --query id \
  -o tsv
~~~

**Warning:** `secret show` **still fetches the secret value into the CLI process** even though the output filter only prints the ID. Do not run it against production secrets unnecessarily; to view metadata only, use metadata listing APIs/commands. Do not test using an Azure CLI user account that has different permissions from the application's identity.

### Propagation Has No Guaranteed Time for Every Case

After a role assignment, caching and propagation delays can occur in Azure RBAC or groups/identities. Do not assume a guaranteed 30-second wait; use bounded waiting/retesting, keep logs, and verify assignments. If a valid role still returns 403 for an extended period, investigate **tenant, principal, parent scope, PIM, deny assignments, vault mode, and firewall**.

## 30. Azure Monitor: Management and Data-Plane Auditing

There are at least two audit streams:

- **Management-plane**: Azure Activity Log for role assignments, vault configuration, and ARM changes.
- **Data-plane**: Key Vault diagnostic resource logs for secret/key/certificate operations per configured categories and diagnostic settings.

| What to observe | Source / Meaning |
|---|---|
| Role assignment create/delete | Activity Log / IAM / PIM audit |
| Permission model switch | Activity Log, Azure Policy compliance |
| Secret get/set/delete outcomes | Key Vault resource audit logs |
| Key crypto operation failures | Key Vault audit logs |
| Purge/delete attempts | Data-plane/management audit depending on operation |
| Private endpoint/network changes | Network/ARM diagnostics |
| Secret/certificate expiry | Key Vault events/monitoring |
| Vault 403/429 and request latency | Resource metrics + application logs |
| Managed identity token errors | Workload logs/identity diagnostics |
| Cost spike | Cost Management, Logs ingestion |

### Check Diagnostic Settings

~~~bash
KV_ID=$(az keyvault show \
  --resource-group "$RG" --name "$KV" \
  --query id -o tsv)

az monitor diagnostic-settings list \
  --resource "$KV_ID" \
  -o json
~~~

This is a **read-only command**. Having a diagnostic setting does not guarantee all audit categories are enabled, logs go to the right workspace, or retention is configured properly. Inspect the configuration and actual log data.

### Example KQL with AzureDiagnostics

When a Log Analytics workspace uses the `AzureDiagnostics` table for Key Vault logs:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| summarize Events = count()
    by bin(TimeGenerated, 1h), ResultType, Resource
| order by TimeGenerated asc
~~~

If using resource-specific tables, verify the **actual table/column names** and write the matching query; never assume `AzureDiagnostics` always receives data. Never log raw secret values, private keys, tokens, or authorization headers. Secret names/URIs and caller identifiers can also be sensitive and require privacy/log access policies.

## 31. Alerting, Access Reviews, and Incident Response

Alert when:

1. Key Vault 403s spike unexpectedly after a release or migration.
2. A new **Key Vault Administrator** role is assigned outside a change window.
3. The permission model is switched from RBAC to access policy outside approved procedures.
4. A principal exhibits unusual secret reads by IP/app/region/time.
5. Unexpected delete/purge/recover operations occur.
6. A certificate/secret nears expiry while rotation remains incomplete.
7. A Private Endpoint becomes unavailable or network egress is blocked.
8. 429s/latency rise and cause multiple applications to fail startup.
9. Managed identity 401/403 errors occur across multiple replicas.
10. Role assignments at a parent scope grant unintended broad permissions.

### Do Not Alert on Every Single Secret Read

An application refreshing its cache every 10 minutes generates scheduled, legitimate reads. Baseline by principal, operation, endpoint, time window, and owner; alerts should use actionable thresholds instead of creating noise.

### Periodic Access Reviews

- Inventory role assignments on the vault and parent scopes.
- Check for unused principals and deleted managed identities.
- Review Administrator/Officer roles in scopes where they are no longer needed.
- Audit group memberships and PIM activations.
- Compare the permission map against actual code/application operations.
- Revoke excess permissions under change approval and smoke-test workloads.
- Record evidence, owners, and rationale for any exceptions.

## 32. Bicep: Managing Role Assignments as Code

Example role assignment on an **existing vault**; the caller must have `roleAssignments/write` per policy:

~~~bicep
@description('Existing Key Vault name')
param vaultName string

@description('Managed identity principal/object ID')
param principalObjectId string

@description('Full ARM role definition ID of Key Vault Secrets User')
param secretsUserRoleDefinitionId string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
}

resource grant 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, principalObjectId, secretsUserRoleDefinitionId)
  scope: vault
  properties: {
    roleDefinitionId: secretsUserRoleDefinitionId
    principalId: principalObjectId
    principalType: 'ServicePrincipal'
  }
}
~~~

**This illustrates a schema that must be verified** against your project's Bicep/ARM versions. The role ID parameter must be the **exact full ARM roleDefinitionId**, not an arbitrary display string. This file does not create the vault, managed identity, or network, nor switch the permission model.

IaC helps:

- Review role/scope changes in pull requests.
- Use deterministic role assignment GUIDs to avoid collisions.
- Detect drift caused by manual IAM edits.
- Manage differences across dev/staging/prod.
- Keep plaintext secrets and UAMI credentials out of the repository.
- Reconcile `principalId` when an identity is recreated.
- Validate scopes and guardrails before deployment.

## 33. Cost and Quotas

Key Vault security design impacts cost:

| Item | Examples |
|---|---|
| Vault/key operations | Secret get/list/set, key crypto operations, certificates |
| Premium/HSM-backed keys | Charges depend on SKU, key type, and pricing meter |
| Networking | Private Endpoints, DNS Resolver, Firewall, egress |
| Compute | App/rotation jobs/Azure Functions/Container Apps |
| Monitoring | Azure Monitor/Log Analytics ingestion/retention |
| Operations | Cert renewal, backup, DR, security reviews |
| Retries | Excessive 403/429s or reading secrets on every request |
| Environment separation | Multiple vaults and policies to manage |

Do not cite a fixed unit price, as pricing depends on **region, tier, key type, operation count, related services, and time**. Measure cost per successful secret retrieval or crypto operation per workload, not just the base vault fee.

### Optimize Without Weakening Security

- Reuse SDK `SecretClient`, credentials, and HTTP connections.
- Cache secrets per an appropriate refresh/rotation SLO instead of an infinite TTL.
- Avoid calling Key Vault on every HTTP request when a secure cache meets requirements.
- Cap retries on permission errors and back off on 429/503s.
- Scope vaults/roles per application instead of using overly broad roles.
- Apply owner/env/cost-center tags, budgets, and alerts.
- Log enough for investigation without logging raw payloads.

## 34. Case Study: E-Commerce, Signing, and Rotation

### Context

An e-commerce product has three workloads:

- **commerce-api** (Spring Boot on Container Apps): only reads DB connection secrets.
- **invoice-signer** (Java worker on AKS): signs invoices using a key.
- **secret-rotator** (Azure Function): rotates passwords periodically.

Requirements:

- No plaintext secrets in Git/CI.
- Workloads cannot grant themselves IAM roles.
- API cannot read the crypto signing key.
- Signing app cannot read the payment provider token.
- Rotation job cannot be granted Owner across the subscription.
- Private Endpoint, auditing, and break-glass runbook in place.

~~~mermaid
flowchart LR
  API["Container App + Managed Identity"] -->|Secrets User| V1["kv-commerce-secrets-prod"]
  SIGN["AKS Worker + Workload Identity"] -->|Crypto User| V2["kv-signing-prod"]
  ROT["Function rotation identity"] -->|Secrets Officer| V1
  SEC["Security / PIM"] --> IAM["Narrow scoped IAM management"]
  IAM -.-> V1
  IAM -.-> V2
  V1 --> MON["Monitor + Audit"]
  V2 --> MON
~~~

### Decisions

1. Two vaults with separate boundaries for secrets and cryptographic keys.
2. A dedicated identity per workload.
3. Secrets User role on `kv-commerce-secrets-prod` for the API.
4. Crypto User role on `kv-signing-prod` for the signer.
5. Secrets Officer role on the secrets vault for the rotator.
6. Separate IAM admin/PIM for role assignment changes.
7. Private endpoint, DNS, and egress verified from each host.
8. Secret rotation includes validation, app refresh, and rollback.
9. Alerts for 403s, role changes, expiry, and crypto failures.
10. Never grant Key Vault Administrator to all apps.

### Incident A: 403 Despite Just Assigning a Role

The team passed the **UAMI clientId** into the role assignment command using `--assignee-object-id`. Fixed by querying `principalId`, verifying the assignment at the right scope, and retesting—without granting Owner.

### Incident B: IAM Correct, App Times Out

The Container Apps environment could not resolve the Key Vault FQDN to the private IP after enabling Private Endpoint. Fixed private DNS/routing without changing Key Vault roles.

### Incident C: Rotator Loses Access After Migration

The old access policy gave the rotator `set` permissions on secrets. After switching to RBAC, the team mapped read permissions for the app but forgot **Secrets Officer** for the rotator. A migration inventory and smoke tests across all service identities are essential, not just checking the main app.

## 35. Guided Practice Lab

> **Safety:** Operate only within an approved **lab subscription, resource group, and Key Vault**. Role assignments, permission models, and network changes affect live access; never touch production vaults, use real secrets, or print secret values.

### Part A — Setup

1. Identify the lab tenant/subscription/resource group and budget.
2. Verify permissions to create vaults, assign roles, and configure networking per policy.
3. Create a new vault using the **Azure RBAC permission model**.
4. Verify soft delete/purge protection and networking settings.
5. Record the Vault URI and ARM resource ID.
6. Create a non-sensitive **demo-config** secret using an operator with write permission.
7. Create/attach a lab managed identity.
8. Retrieve `principalId`/`clientId` and document the purpose of each ID.
9. Inspect role definitions for Secrets User, Secrets Officer, and Key Vault Reader.
10. Build an expected-access matrix before granting permissions.

### Part B — Grant and Test RBAC

1. Assign Secrets User at vault scope to the lab managed identity.
2. Run `az role assignment list --include-inherited` to verify the assignment.
3. Wait for propagation.
4. Read the lab secret from the actual workload identity/host.
5. Never print `getValue()` or the full secret JSON.
6. Test write/set using the reader identity: it must be denied.
7. Assign Secrets Officer to a separate rotation identity.
8. Create a new version of `demo-config` using the rotator and audit the operation.
9. Inspect assignment inheritance/groups/PIM in the Portal.
10. Clean up lab assignments per change approval when finished.

### Part C — Network Testing

1. Test vault DNS/HTTPS from a test Container App/VM.
2. If using a Private Endpoint, verify private IP resolution.
3. Confirm network reachability before concluding an error is RBAC-related.
4. Test an unauthorized principal from the same network to observe a role-based 403.
5. Test a disallowed network path in an isolated environment to distinguish a firewall error.
6. Confirm the SDK's actual principal via provider config (without logging tokens).
7. Compare local developer credentials with the managed identity.
8. Inspect logs/metrics for denied requests.
9. Never enable public internet access to bypass network policy.
10. Restore lab network configuration after testing.

### Part D — Migration Planning

1. Inventory access policies of a **hypothetical** vault.
2. Map principals/actions to minimal built-in roles.
3. Check permissions inherited from subscription/RG.
4. Prepare role assignments ahead of cutover.
5. Build a smoke-test matrix for secrets reader, rotator, crypto user, and certificate consumer.
6. Draft a change window/rollback/incident escalation plan.
7. Simulate role propagation not yet taking effect.
8. Simulate rotator 403 post-migration and propose remediation.
9. Propose an Azure Policy guardrail enforcing RBAC mode.
10. Write a least-privilege and audit evidence report.

## 36. Self-Check Questions

**Q1.** How do secrets, keys, and certificates differ in purpose within Key Vault?

**Q2.** Which operations distinguish the management plane from the data plane?

**Q3.** Why can't Contributor or Key Vault Contributor read secrets in RBAC mode?

**Q4.** How do `dataActions` differ from `actions` in a role definition?

**Q5.** Do access policies still grant data-plane access after RBAC mode is enabled?

**Q6.** How do principal, role definition, role assignment, and scope differ?

**Q7.** Which vaults can be affected by a role assignment at the resource group level?

**Q8.** Why is Key Vault Administrator at the subscription level overly broad?

**Q9.** Can Key Vault Reader read secret values?

**Q10.** Which two workloads should use Secrets User vs. Secrets Officer?

**Q11.** How do Crypto User and Crypto Officer differ in responsibility?

**Q12.** Does Certificates User automatically grant read access to all arbitrary secrets in a vault?

**Q13.** Who is authorized to create an Azure role assignment for a managed identity?

**Q14.** What is the specialized role of Key Vault Data Access Administrator?

**Q15.** How does a UAMI `clientId` differ from `principalId`?

**Q16.** When can a system-assigned managed identity change its `principalId`?

**Q17.** Can an identity with Secrets User still receive 403 due to the vault firewall?

**Q18.** Does a Private Endpoint automatically grant RBAC permissions to an application?

**Q19.** Why should you never switch permission models without an inventory?

**Q20.** Why must rotators and cert consumers be checked during migration, not just reader apps?

**Q21.** How does Azure Policy help prevent bypassing RBAC via permission model changes?

**Q22.** Why might a newly assigned role still return 403 for a few minutes?

**Q23.** Does a local app using DefaultAzureCredential necessarily use the same principal as the app on Azure?

**Q24.** Why should an SDK `getSecret` test never print the secret value?

**Q25.** How does inspecting role assignments differ from testing a data-plane operation?

**Q26.** Does secret rotation automatically change the database password when only a new secret version is set?

**Q27.** What do soft delete and purge protection solve, and do they replace backups?

**Q28.** How do management-plane audit logs differ from data-plane audit logs?

**Q29.** Why must Owner/Admin permissions at parent scopes be included in access reviews?

**Q30.** Why shouldn't Secrets Officer be assigned to every read-only application?

**Q31.** Why is reading private key contents different from performing a crypto operation in Key Vault?

**Q32.** What determines whether to choose one or multiple vaults for security boundaries?

**Completion criteria:** Learners accurately distinguish permission models and management/data planes, select least-privilege roles, assign Secrets User to a managed identity by `principalId` at vault scope, verify actual data-plane access from the right workload/network, explain 403/propagation/firewall errors, plan an RBAC migration, and cover security governance, rotation, logging, and cost.

## Conclusion

**Key Vault authorization with Azure RBAC** means controlling **which principal** holds **which role and data actions** at **which scope** under **which permission model**. **Contributor** is a resource-management role and does not inherently grant reading secret values in RBAC mode. Applications that only need to read secrets should start with **Key Vault Secrets User**; signing workloads use crypto roles, rotation identities use appropriate write permissions, and role assignments are governed by IAM/PIM at narrow scopes.

A secure Azure system also relies on **Microsoft Entra ID/managed identities, Private Endpoints and DNS/firewalls, Azure Policy guardrails, monitoring/auditing, propagation-aware troubleshooting, rotation, soft delete, and access reviews**. Always test the real API from the workload's actual identity and network path; **a succeeded role assignment is not proof of secure data access**, and the fix for a 403 should never default to granting subscription-wide Administrator.

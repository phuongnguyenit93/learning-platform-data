# Key Management and Cryptographic Operations with Key Vault

> **Chapter:** Secrets, Keys, and Certificates  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data. Learn how to deploy, monitor, protect, and control costs of an application architecture on Azure.

## Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **Azure Key Vault Keys, Secrets, and Certificates**, Key Vault Standard/Premium, and **Azure Managed HSM**, along with the trust boundaries of cryptographic keys.
2. Explain the differences between **RSA asymmetric encryption**, **signing/signature verification**, **key wrapping/unwrapping**, and **AES-256-GCM symmetric encryption**, and know which operations are unsuitable for encrypting large files.
3. Govern the key lifecycle: **creation, enabling/disabling, validity periods, versioning, rotation, soft delete, purge protection, backup/restore, and decommissioning**.
4. Grant permissions using **Microsoft Entra ID, managed identity, and Azure RBAC** at least-privilege scope; understand the differences between the control plane, data plane, and legacy access-policy model.
5. Perform cryptographic operations safely with **Azure CLI and the Azure SDK for Java**: KeyClient, CryptographyClient, RSA-OAEP-256, wrap/unwrap, and RSA sign/verify.
6. Design **envelope encryption**: generate a local data encryption key (DEK), use AES-GCM for payloads, use a Key Vault key-encryption key (KEK) to protect the DEK, and store the versioned key ID.
7. Connect **Private Endpoint, Private DNS, and TLS**, configure auditing, monitor 401/403/404/429 errors, and analyze latency and cost.
8. Identify risk scenarios: accidental key deletion, rotation breaking decryption, overly broad crypto permissions, nonce reuse, plaintext DEK exposure, unauthenticated encryption, and retry flaws.
9. Design a lab, permission test matrix, incident runbook, and production checklist for Azure applications.

## 1. Context: Data Is Encrypted, But Who Holds the Key?

An e-commerce system stores invoice PDFs in Azure Blob Storage, identity records in a database, and sensitive content that must be encrypted before storage. The Java application runs on Azure App Service or Azure Container Apps and uses a **managed identity** to call Key Vault.

If the application stores a fixed AES encryption key in `application.properties`, a Docker image, or Git, leaking that key lets an attacker decrypt the entire data store. If every developer holds `Key Vault Administrator` with key-deletion permissions, weak authorization still undermines encryption.

You must clearly design:

- **Which sensitive data requires application-layer encryption?** Not every file needs custom encryption because Azure Storage already supports encryption at rest; the requirement may stem from compliance or tenant separation.
- **Which key protects the data?** Distinguish the **Data Encryption Key (DEK)** from the **Key Encryption Key (KEK)**.
- **Who can invoke which operation?** Reading key metadata, wrapping, unwrapping, encrypting, decrypting, and managing lifecycle are distinct permissions.
- **Can the key be exported in plaintext?** Asymmetric keys generated/stored in Key Vault/HSM have a protection boundary; the private key is used via service crypto operations rather than read by the app like a secret.
- **If a key is disabled, deleted, or rotated, can old data still be read?** You must store the version ID and retain valid key history.
- **Do networking, logging, and recovery meet security requirements?** Key Vault authorization does not replace Private Link/TLS, auditing, or business authorization.

~~~mermaid
flowchart LR
    U["User"]
    API["Java API\nBusiness authorization"]
    MI["Managed identity\nEntra ID"]
    KV["Azure Key Vault\nKEK asymmetric key"]
    AES["Local AES-256-GCM\nDEK per object"]
    BLOB["Azure Blob Storage\nEncrypted object"]
    DB["Metadata DB\nWrapped DEK + key ID"]
    OBS["Azure Monitor\nDiagnostics + alerts"]
    U --> API
    MI -.->|"Token"| API
    API --> AES
    AES -->|"Wrap / unwrap DEK"| KV
    AES -->|"Ciphertext"| BLOB
    API -->|"Metadata"| DB
    KV -.-> OBS
    API -.-> OBS
~~~

**Running example:** Each invoice gets a random DEK. The invoice payload is encrypted with AES-GCM in Java; Key Vault only handles **wrapping/unwrapping the small DEK**, never receiving the multi-GiB file itself.

## 2. Key Vault Stores Keys, Secrets, and Certificates Differently

### 2.1. Three Object Types

| Type | Purpose | Appropriate API/SDK | Warning |
| --- | --- | --- | --- |
| **Keys** | Manages asymmetric keys and crypto operations like encrypt/decrypt, wrap/unwrap, sign/verify | `azure-security-keyvault-keys` | Not an arbitrary secret value store |
| **Secrets** | Stores passwords, API keys, connection strings, and byte/text secrets within limits | `azure-security-keyvault-secrets` | Reading a secret returns the **plaintext value** to an authorized principal |
| **Certificates** | Manages TLS/X.509 certificate lifecycle, certificate policy, and key/secret linkage | `azure-security-keyvault-certificates` | A public certificate does not imply arbitrary private key exportability |

A **Key Vault key** has metadata, a public key (for asymmetric keys), policy, and crypto operations. A **Secret** is read as a value, so storing an AES master key in a secret allows any principal with `get secret` to obtain the plaintext key. To protect a key inside a managed boundary, evaluate **Keys/HSM + wrap/unwrap** instead of downloading a key from a secret into the app.

### 2.2. Standard, Premium, and Managed HSM

| Option | Characteristics | Best fit |
| --- | --- | --- |
| **Azure Key Vault Standard** | Stores software-protected keys plus secrets/certs per service capabilities | Most applications needing key management and crypto operations |
| **Azure Key Vault Premium** | Adds supported HSM-protected key options | Workloads requiring HSM-backed key protection and matching policies |
| **Azure Key Vault Managed HSM** | Dedicated HSM service for keys with a separate administration/backup, network, and billing model | Strict regulatory controls or dedicated HSM administration needs |

Do not assume “Premium” turns **every key** into an HSM-protected key: when creating a key, you must choose the appropriate **key type/storage target**. Features, compliance standards, regions, and pricing are subject to change; verify service limits and specific certification requirements before going to production.

### 2.3. Do Not Confuse Key Vault and Managed HSM

- A vault has an endpoint like `https://<vault-name>.vault.azure.net/`.
- Managed HSM has its own endpoint, permissions, security domain, and backup model.
- `az keyvault key ...` commands and the Java Key Vault SDK examples here focus on Key Vault capabilities; do not assume examples in this lesson apply verbatim to Managed HSM.
- Key Vault Premium HSM keys and Managed HSM do not share every feature or limit.
- Before designing for FIPS/compliance requirements, cross-check official certification documentation and organization-approved SKUs/algorithms.

### 2.4. Key Identifiers Include Versions

A Key Vault key can be referenced as:

~~~text
https://kv-orders-prod.vault.azure.net/keys/invoice-kek
https://kv-orders-prod.vault.azure.net/keys/invoice-kek/KEY_VERSION
~~~

- The first URI is a **versionless key identifier**: operations can target the latest/current version per API/SDK semantics.
- The second URI is a **versioned key identifier**: it pins a specific key version.
- When encrypting long-lived data, **store the exact versioned key ID used** in envelope metadata. Never assume the latest version can decrypt old data.
- Version IDs are service-generated values; clients must never guess them from dates or assume a different key name represents the same key.

## 3. Algorithms and Operations to Understand

### 3.1. Asymmetric Keys: RSA and EC

**RSA** has public/private keys and supports operations depending on configured key type/operations:

- Encrypting/decrypting **very small payloads** with RSA-OAEP when supported.
- **Wrapping/unwrapping** short symmetric keys like an AES DEK.
- **Signing/verifying** using a suitable signature algorithm.

**Elliptic Curve (EC)** keys in Key Vault are typically used for **ECDSA digital signatures**, not as a drop-in replacement for `RSA-OAEP` encrypt/wrap. Never create an EC key and call `encrypt(RSA_OAEP_256, ...)`.

### 3.2. RSA-OAEP-256 Is for Small Messages

RSA-2048 has a 256-byte modulus. With OAEP using SHA-256, the maximum plaintext length per standard bounds is:

\[
mLen \le k - 2hLen - 2 = 256 - 64 - 2 = 190\ \text{bytes}.
\]

Therefore, **never encrypt a 10 MiB PDF file directly with RSA-OAEP-256**. Use hybrid/envelope encryption: AES-GCM handles the bulk payload while RSA-OAEP-256 only wraps the 32-byte DEK.

With RSA-3072/4096, the payload limit is larger, but that still does not make RSA a bulk encryption algorithm. Never use RSA-OAEP with the wrong padding; avoid RSA PKCS#1 v1.5 encryption in new designs unless an evaluated compatibility requirement demands it.

### 3.3. AES-256-GCM Is Authenticated Encryption

AES-GCM provides **confidentiality and an integrity/authentication tag** for ciphertext when used properly:

- 256-bit AES key (32 bytes).
- Typically 96-bit nonce/IV (12 bytes).
- Commonly 128-bit authentication tag.
- **AAD** (Additional Authenticated Data) to bind tenant ID, object ID, and schema version without encrypting them.
- **Never reuse the same IV with the same DEK**: doing so breaks GCM's security guarantees.

Good pattern: **a fresh random DEK per object**, a fresh random IV, encrypt the file with AES-GCM, and wrap the DEK with Key Vault. For very large files or multi-chunk streaming, use a separately designed and verified chunked AEAD protocol rather than reusing the same nonce across chunks.

### 3.4. Encrypt/Decrypt, Wrap/Unwrap, and Sign/Verify Are Not the Same

| Key Vault Operation | Input | Output | Purpose |
| --- | --- | --- | --- |
| **Encrypt** | Small plaintext + algorithm | Ciphertext | Encrypts small data per key algorithm |
| **Decrypt** | Ciphertext + algorithm | Plaintext | Decrypts small data |
| **Wrap Key** | Short raw DEK + key wrap algorithm | Wrapped DEK | Protects a symmetric key used for payloads |
| **Unwrap Key** | Wrapped DEK + algorithm | Raw DEK | Recovers DEK for local decryption |
| **Sign** | Digest/input per API + signature algorithm | Digital signature | Proves data origin/integrity |
| **Verify** | Digest + signature + algorithm | Verification result | Verifies a signature |
| **Get key** | Key name/version | Permitted public metadata/key material | Does not export HSM private keys |

**Encryption does not create a digital signature**, and a digital signature does not keep content confidential. Use AEAD for payload integrity; use signatures when you need proof of the signer's origin and an appropriate PKI/trust model.

## 4. Key Lifecycle in Key Vault

### 4.1. States and Operations

~~~mermaid
flowchart LR
    C["Create / import"]
    A["Enabled key version"]
    R["Rotate\nNew version"]
    D["Disabled / expired"]
    S["Soft-deleted"]
    RE["Recover"]
    P["Purge after rules"]
    C --> A
    A --> R
    R --> A
    A --> D
    A --> S
    D --> A
    S --> RE --> A
    S --> P
~~~

This is a **conceptual diagram** and does not mean every state transition is unrestricted. Purge protection, retention, permissions, expiration, service restrictions, and incident policies can block certain transitions.

### 4.2. Key Versions and Validity Periods

A key can have:

- A stable **name** like `invoice-kek`.
- A new **version** after rotation.
- **Enabled/disabled** state.
- **Not-before (nbf)** and **expires (exp)** timestamps.
- **Allowed key operations** (`encrypt`, `decrypt`, `wrapKey`, `unwrapKey`, `sign`, `verify`) per features and policy.
- **Tags** for owner, data classification, and governance.
- A **rotation policy** with schedule/conditions per key type and service capabilities.

**Key expiration** and **encrypted data that still must be readable for 7 years** are two separate concerns. If an old key version is disabled/deleted and can no longer unwrap, old ciphertext can become unreadable even though the file itself is intact.

### 4.3. Safe Rotation

1. Review the rotation reason: periodic schedule, compliance change, or compromise.
2. Identify existing key versions and data referencing each version.
3. Create/rotate to a **new key version** per policy.
4. Switch **new encrypt/wrap** calls to the new version.
5. **Keep old versions** available for old ciphertext until **rewrapping** completes or retention ends.
6. With envelope encryption, **rewrap DEKs** with the new KEK without needing to download/re-decrypt entire data files when done with proper permissions and procedures.
7. Test decrypting data across multiple versions and test rollback.
8. Disable/decommission the old key version only after sign-off and inventory confirmation that no dependencies remain.

Rotation **does not automatically re-encrypt all Blob/DB ciphertext** encrypted by the application itself. For Azure service-integrated CMK, refresh behavior varies by resource integration and settings; do not extrapolate from that to app-managed envelopes.

### 4.4. Soft Delete and Purge Protection

- **Soft delete** retains deleted vault/key objects during the retention window per service capabilities.
- **Purge protection** prevents permanent deletion before retention ends per applied policy.
- **Recover** differs from **purge**. Recover can restore a soft-deleted object while still within retention and with sufficient permissions.
- Never treat purge permissions as routine lab cleanup.
- Never assume purge protection can be turned off once enabled; design environments and retention up front.

For systems using **customer-managed keys (CMK)** for Azure Storage, databases, or compute, losing a key can render resources unable to decrypt data. Soft delete and purge protection are typically critical prerequisites in CMK designs.

### 4.5. Key Backup/Restore Is Not Downloading the Private Key

Key Vault provides **key object backup/restore** APIs subject to supported conditions; backups are service-protected/encrypted and **do not export plaintext private keys**. Restore scope may have constraints on subscription, geography, vault type, and key protection boundary. Test on the exact SKU/region and follow your DR runbook.

For HSM-backed keys, never assume you can extract the private key as PEM to move to arbitrary external systems. **Key backups + stored ciphertext + accurate key version/DEK manifests** together form a meaningful recovery plan.

## 5. Azure RBAC, Managed Identity, and Permission Scope

### 5.1. Control Plane vs. Data Plane

**Control plane (Azure Resource Manager):** creating vaults, configuring networking, tags, diagnostic settings, access models, and resources.

**Data plane (Key Vault endpoint):** creating/managing keys, wrap/unwrap, encrypt/decrypt, sign/verify, and specific key/secret/cert operations.

A principal with Azure `Reader` on a resource group **does not inherently** have `unwrapKey`. Conversely, a principal with permissions to edit legacy access policies or assign Azure RBAC roles via IAM may have **indirect privilege-escalation paths**; review administrative privileges carefully.

### 5.2. Commonly Used Roles

| Built-in Role | General Purpose | Do Not Use When |
| --- | --- | --- |
| **Key Vault Crypto User** | Performs cryptographic operations with keys at the assigned scope | Unwrap/decrypt is not needed, or the role grants excessive rights |
| **Key Vault Crypto Officer** | Administers keys and supported crypto operations | It is merely a data-encrypting runtime |
| **Key Vault Administrator** | Administers the vault data plane across objects; very powerful | Ordinary business applications |
| **Key Vault Reader** | Reads object metadata per supported role; does not read secret values or private keys | Encrypt/unwrap operations are needed |
| **Key Vault Secrets User** | Reads secret values per role | Only Key Vault keys are needed |
| **Key Vault Crypto Service Encryption User** | Role for certain CMK service integrations when configured appropriately | Assigned broadly to users/apps without integration |
| **Azure Owner/User Access Administrator** | Holds ARM-scope role assignment permissions | Granted by default to workloads |

Roles **do not have identical semantics**: verify `DataActions`/Key Vault RBAC support and scope. An application needing only `wrapKey` may warrant a custom role or tailored policy if a built-in role is too broad; avoid adding `unwrapKey` when there is no business need to decrypt.

### 5.3. RBAC vs. Legacy Access Policies

Key Vault supports authorization models depending on vault/configuration:

- **Azure RBAC authorization:** role assignments at an appropriate scope, generally preferred for consistent permission governance.
- **Vault access policies (legacy):** vault-level permissions; carries the risk that control-plane admins able to edit policies can grant themselves key/secret access if unchecked.

**Do not assume both RBAC and access policies apply simultaneously as two layers.** Whichever authorization model is configured on the vault governs behavior. When switching models in production, preflight role assignments and avoid outages.

### 5.4. Managed Identity for Java

~~~text
Java application on Azure
  → Managed identity / workload identity
  → Microsoft Entra OAuth token
  → Key Vault HTTPS endpoint
  → Evaluate RBAC/data permissions + network
  → Crypto result
~~~

Prefer separate identities by **environment** and **function**: `mi-orders-encrypt` may need only public encrypt/wrap; `mi-orders-decrypt` needs unwrap at an approved scope; the rotation operator uses a separate identity.

**Never grant Key Vault Administrator to a runtime** just to silence a `403`. Inspect the principal object ID, assignment scope, role, propagation, vault firewall, and permitted key operations.


## 6. Azure CLI: Inspecting a Vault, Creating Keys, and Viewing Versions

### 6.1. Practice Prerequisites

- An existing, authorized Azure subscription, resource group, and **lab Key Vault**.
- The vault uses Azure RBAC authorization, or you know explicitly that it uses legacy access policies.
- The operator managing keys has separate privileges; **the application runtime does not need create/delete key permissions**.
- DNS/TLS and firewall/Private Endpoint allow the client to reach the vault endpoint.
- Before creating billable keys or HSM operations, verify SKU/region, budget, and resource owner.

Commands in this lesson are examples only; **never run them on production** or vaults with real data without approval.

### 6.2. Confirm Azure Context

~~~bash
az login

az account show \
  --query "{subscription:name,subscriptionId:id,tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-crypto-lab"
VAULT="kv-crypto-lab-unique"
KEY_NAME="invoice-kek"

az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --output json
~~~

Inspect authorization model, purge protection, soft-delete retention, network rules, and location in the actual output. `az keyvault show` is metadata/control-plane; success here **does not prove** `unwrapKey` permission on the data plane.

### 6.3. Read Keys and Versions

~~~bash
az keyvault key list \
  --vault-name "$VAULT" \
  --output table

az keyvault key show \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output json

az keyvault key list-versions \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output table
~~~

The `key ...` commands require a network path and appropriate data-plane permissions. Output can include the **public key** and key metadata, never plaintext RSA private keys. Do not expose sensitive endpoints or metadata in unprotected logs.

### 6.4. Create a 3072-bit RSA Key in a Lab Vault

~~~bash
# WRITE OPERATION: run only with proper permissions and approval.
az keyvault key create \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --kty RSA \
  --size 3072 \
  --output json
~~~

`--kty RSA` creates a software-protected RSA key per SKU capabilities. For an HSM-backed RSA key on an eligible vault, specify the corresponding type such as `RSA-HSM` where supported by Azure CLI/service. **Vault Premium does not automatically make every key HSM-backed.**

A lab vault should use dedicated key names rather than production key IDs. Do not run key creation/rotation repeatedly to “test idempotency” without understanding how the command behaves with existing key versions.

### 6.5. Inspecting RBAC Assignments Differs from Crypto Permissions

~~~bash
VAULT_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query id -o tsv)

az role assignment list \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
~~~

RBAC permissions come from direct assignments, parent scopes, and group memberships; in legacy access policy mode, inspect the vault policy separately. `role assignment list` output alone does not serve as a live test of every key operation.

### 6.6. Grant Crypto User to a Managed Identity (When Approved)

~~~bash
PRINCIPAL_OBJECT_ID="<MANAGED_IDENTITY_PRINCIPAL_OBJECT_ID>"

# PERMISSION CHANGE: execute only by an authorized IAM operator.
az role assignment create \
  --assignee-object-id "$PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Crypto User" \
  --scope "$VAULT_ID"
~~~

- The ID must be the managed identity's **principal object ID**, not its client ID/application ID.
- `Key Vault Crypto User` grants the crypto operations defined by the role; inspect `DataActions`, as the role may be broader than wrap-only needs.
- If only one workload uses the vault, vault scope may fit. With multiple workloads, consider separating vaults, keys, or supported custom roles/scopes.
- Role assignments may take time to propagate; never escalate to `Key Vault Administrator`.
- If the vault uses legacy access policies, an RBAC **role assignment may not grant the expected data-plane permissions** on that vault.

### 6.7. Read Rotation Policy

~~~bash
az keyvault key rotation-policy show \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output json

az keyvault key rotate --help
az keyvault key rotation-policy update --help
~~~

This lesson only uses `show` for reading. Never run rotate/delete/disable/purge against a vault containing real data. When configuring automatic rotation, check support by key type/SKU/version, schedule/notifications, and the app's requirement to keep old key versions for decryption.

### 6.8. Before Disabling or Deleting an Old Key Version

Before making changes:

1. Locate envelope records still referencing that version.
2. Run decrypt/unwrap regression tests on old ciphertext.
3. Rewrap wrapped DEKs to the new KEK version if policy requires it.
4. Verify backups, retention, and purge protection.
5. Obtain change approval and prepare a rollback plan.
6. Only then disable the key version on schedule.

**Deleting and purging keys are not routine housekeeping.** Accidentally deleted keys cannot be replaced by creating a new key with the same name to decrypt prior data.

## 7. Java SDK for Azure Key Vault Keys

### 7.1. Maven Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-security-keyvault-keys</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
    </dependency>
</dependencies>
~~~

These dependencies require versions managed by a Maven parent POM/`dependencyManagement` or the Azure SDK BOM. Example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <azure.sdk.bom.version>REPLACE_WITH_APPROVED_BOM_VERSION</azure.sdk.bom.version>
</properties>

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
~~~

When saving into `pom.xml`, keep the exact Maven property syntax with dollar sign, braces, and `azure.sdk.bom.version`. The BOM version must be an approved version, not the placeholder string. For Java 17+, verify library and compiler compatibility.

### 7.2. Configuration and Authentication

~~~text
KEY_VAULT_URL=https://kv-crypto-lab-unique.vault.azure.net/
KEY_NAME=invoice-kek
~~~

Use `DefaultAzureCredential` to obtain Microsoft Entra ID tokens. In local dev, credentials can come from Azure CLI/IDE. On Azure App Service, Container Apps, or AKS, select the appropriate **managed/workload identity** and verify which principal is actually being used.

### 7.3. KeyClient and CryptographyClient

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.KeyClient;
import com.azure.security.keyvault.keys.KeyClientBuilder;
import com.azure.security.keyvault.keys.models.KeyVaultKey;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;

public final class VaultClients {
    private VaultClients() {}

    public static TokenCredential credential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    public static KeyClient keyClient(
            String vaultUrl, TokenCredential credential) {
        return new KeyClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(credential)
            .buildClient();
    }

    public static CryptographyClient forVersion(
            String keyVersionId, TokenCredential credential) {
        return new CryptographyClientBuilder()
            .keyIdentifier(keyVersionId)
            .credential(credential)
            .buildClient();
    }

    public static String latestKeyId(
            KeyClient client, String name) {
        KeyVaultKey key = client.getKey(name);
        return key.getId(); // includes version
    }
}
~~~

**Important limitations:**

- `getKey` requires permission to read key metadata; do not assume every API succeeds under a generic data role.
- `CryptographyClient` should be constructed with a **versioned key identifier** when data requires long-term decryption. A versionless ID fits some “latest” encrypt/wrap flows, provided you record the actual version returned/used.
- Never accept an arbitrary `vaultUrl` or `keyVersionId` from an HTTP request and allow unwrapping; allowlist vaults/keys per tenant/workload.
- Share clients, HTTP transport, and token providers across lifecycles rather than recreating them per byte or per call.
- SDKs may optimize public-key operations locally; do not assume every call on `CryptographyClient` sends a remote HTTP request.

### 7.4. Key Creation in Java Is for Provisioning Only

~~~java
import com.azure.security.keyvault.keys.KeyClient;
import com.azure.security.keyvault.keys.models.KeyVaultKey;

KeyVaultKey created = keyClient.createRsaKey("invoice-kek");
System.out.println("Key version ID: " + created.getId());
~~~

This is a snippet inside a context where `keyClient` is already configured. **Never create keys inside a request handler**; the runtime identity should not have create/rotate/delete rights. To specify key size, type, operations, tags, and expiration, use options APIs or verified IaC provisioning matched to your SDK version.


## 8. Encrypting and Decrypting a Small Message with RSA-OAEP-256

### 8.1. Java Sample Suitable for Lab

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.EncryptionAlgorithm;
import com.azure.security.keyvault.keys.cryptography.models.EncryptResult;
import com.azure.security.keyvault.keys.cryptography.models.DecryptResult;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class RsaSmallMessageDemo {
    public static void main(String[] args) {
        String keyId = System.getenv("KEY_VERSIONED_ID");
        if (keyId == null || keyId.isBlank()) {
            throw new IllegalStateException("KEY_VERSIONED_ID required");
        }

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();
        CryptographyClient crypto =
            new CryptographyClientBuilder()
                .keyIdentifier(keyId)
                .credential(credential)
                .buildClient();

        byte[] plaintext = "Test order code"
            .getBytes(StandardCharsets.UTF_8);

        EncryptResult encrypted =
            crypto.encrypt(EncryptionAlgorithm.RSA_OAEP_256, plaintext);
        DecryptResult decrypted =
            crypto.decrypt(
                EncryptionAlgorithm.RSA_OAEP_256,
                encrypted.getCipherText()
            );

        System.out.println(
            "Round-trip valid: " +
            Arrays.equals(plaintext, decrypted.getPlainText())
        );

        // Do not write plaintext/ciphertext/credentials to logs.
        Arrays.fill(plaintext, (byte) 0);
    }
}
~~~

**Use only with an RSA key and a small enough payload.** For RSA-2048 + OAEP-SHA256, plaintext is limited to 190 bytes. The RSA key must permit the algorithm and key operations, and the app identity needs crypto permissions. UTF-8 byte length, **not character count**, determines the input limit.

### 8.2. What Metadata Must Be Stored with Ciphertext?

~~~json
{
  "formatVersion": 1,
  "algorithm": "RSA-OAEP-256",
  "keyId": "https://kv-crypto-lab-unique.vault.azure.net/keys/invoice-kek/EXAMPLE_VERSION",
  "ciphertextBase64": "BASE64_EXAMPLE"
}
~~~

This is an **illustrative data structure**, not a valid encrypted payload. The key ID must reference the version used and be validated against approved vaults/keys. The payload can live in Blob Storage/DB, while still requiring business authorization and data protection.

### 8.3. Why Not Split a PDF into Many RSA Blocks?

Encrypting small chunks with RSA and concatenating them manually:

- Generates massive remote crypto operations, high latency, and high cost.
- Does not create an authenticated file format; there is no cross-chunk integrity.
- Makes key-size/padding bounds complex and error-prone.
- Makes rotation and migration much harder.

Practical solution: **hybrid/envelope encryption** with AES-GCM for content and an RSA key only to **wrap/unwrap the DEK**.

## 9. Wrapping and Unwrapping an AES Key

### 9.1. Key Wrap Operations

`wrapKey` accepts a short raw DEK and returns a **wrapped DEK**. `unwrapKey` accepts a wrapped DEK and returns the raw DEK to an authorized caller.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.KeyWrapAlgorithm;
import com.azure.security.keyvault.keys.cryptography.models.WrapResult;
import com.azure.security.keyvault.keys.cryptography.models.UnwrapResult;

import javax.crypto.KeyGenerator;
import java.security.MessageDigest;
import java.util.Arrays;

public final class RsaWrapDemo {
    public static void main(String[] args) throws Exception {
        String keyId = System.getenv("KEY_VERSIONED_ID");
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();
        CryptographyClient crypto =
            new CryptographyClientBuilder()
                .keyIdentifier(keyId)
                .credential(credential)
                .buildClient();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        byte[] dek = generator.generateKey().getEncoded();

        WrapResult wrapped = crypto.wrapKey(
            KeyWrapAlgorithm.RSA_OAEP_256, dek
        );
        UnwrapResult unwrapped = crypto.unwrapKey(
            KeyWrapAlgorithm.RSA_OAEP_256,
            wrapped.getEncryptedKey()
        );

        System.out.println(
            "DEK matches: " +
            MessageDigest.isEqual(dek, unwrapped.getKey())
        );

        Arrays.fill(dek, (byte) 0);
        Arrays.fill(unwrapped.getKey(), (byte) 0);
    }
}
~~~

**Note:** `Arrays.fill` only attempts to wipe the arrays referenced in code; the **JVM/SDK may have created copies**. Never claim plaintext DEKs are guaranteed to be wiped from all memory. Raw DEKs must never enter logs, traces, message queues, or client browsers.

### 9.2. KEK, DEK, and Wrapped DEK

| Component | Where is it stored? | Who can use it? |
| --- | --- | --- |
| **KEK** (RSA private key) | Key Vault/HSM boundary per configuration | Authorized cryptographic operations only |
| **DEK** (AES-256) | Temporarily in app memory during processing | Authenticated, authorized runtime |
| **Wrapped DEK** | Envelope metadata/DB/Blob | Protected by integrity and access policy |
| **Ciphertext** | Blob Storage/DB | Readable only by authorized principals |
| **Key version ID** | Envelope metadata | Must be allowlisted and verified for vault/key |
| **AAD/IV/tag** | Envelope per defined schema | AAD must match on decrypt; IV must never repeat per DEK |

A wrapped DEK **is not a plaintext secret**, yet object metadata/identifiers still should not be exposed publicly because they can aid attackers. Protect storage and avoid granting `unwrapKey` too broadly.

### 9.3. Principle of Separating Read and Write Permissions

An application that only needs **encrypt/write** should consider:

- Generating the DEK locally.
- Calling `wrapKey` with an approved KEK.
- Writing ciphertext/wrapped DEK to appropriate storage.
- **Not necessarily needing `unwrapKey`** if it does not serve downloads/decryption.

An application that needs **decrypt/read** requires storage read access, `unwrapKey`, and **business authorization**. Custom roles, separate identities, or separate vaults can enforce this split when supported and required, rather than treating `Key Vault Crypto User` as “wrap-only”.

### 9.4. Never Recreate a KEK to Read Old Data

When a version is lost, creating a new key with the same name does not recreate the previous private key. A wrapped DEK is bound to **specific key material**, not just a key name. Thus version pinning, key backup/recovery, and retention are core requirements.

## 10. Envelope Encryption for Files and Objects

### 10.1. Steps to Upload an Object

1. API authenticates user and tenant; determines the object's encryption policy.
2. Generates a **new AES-256 DEK** using a secure random provider.
3. Generates a **new 12-byte IV**, with AAD as a stable representation of tenant/object ID and schema.
4. Encrypts plaintext with **AES/GCM/NoPadding**, producing ciphertext **with authentication tag**.
5. Calls Key Vault `wrapKey` using RSA-OAEP-256 and the **versioned KEK ID**.
6. Saves ciphertext in Blob Storage and the envelope: `keyId`, `algorithm`, `wrappedDek`, `iv`, `aadVersion`, tag format.
7. Marks object READY in the DB once data and metadata are committed/verified.
8. Never logs the DEK, plaintext, or full decrypted content.

~~~mermaid
flowchart TB
    P["Plaintext file"]
    D["Random AES DEK 256 bits"]
    N["Unique IV + stable AAD"]
    AES["AES-256-GCM"]
    KV["Key Vault RSA KEK\nwrapKey"]
    C["Ciphertext + GCM tag"]
    W["Wrapped DEK"]
    E["Envelope metadata\nkey version ID, IV, AAD version"]
    P --> AES
    D --> AES
    N --> AES
    D --> KV
    AES --> C
    KV --> W
    W --> E
    N --> E
    C --> S["Blob / data store"]
    E --> S
~~~

### 10.2. Complete Java Example for Small Payloads Using Envelope Pattern

To make the sequence clear for learners, this example holds the payload in a byte array **for lab only**. For large files, use a vetted streaming/chunked AEAD design rather than loading gigabytes with `Files.readAllBytes`.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.KeyWrapAlgorithm;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

public final class EnvelopeCryptoDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String WRAP_ALGORITHM = "RSA-OAEP-256";
    private static final int GCM_TAG_BITS = 128;
    private static final int GCM_IV_BYTES = 12;

    // Production requires versioned serialization, bounds checks,
    // authentication, and a separately verified storage schema.
    public record Envelope(
        String keyVersionId,
        byte[] iv,
        byte[] wrappedDek,
        byte[] ciphertextAndTag
    ) {}

    private static CryptographyClient crypto(String keyVersionId) {
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();
        return new CryptographyClientBuilder()
            .keyIdentifier(keyVersionId)
            .credential(credential)
            .buildClient();
    }

    private static byte[] aad(String tenantId, String objectId) {
        // Use only server-side IDs validated against schema.
        String canonical = "v1|tenant=" + tenantId + "|object=" + objectId;
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static Envelope encrypt(
            String approvedKeyVersionId,
            String tenantId,
            String objectId,
            byte[] plaintext) throws Exception {

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dek = generator.generateKey();
        byte[] rawDek = dek.getEncoded();

        try {
            byte[] iv = new byte[GCM_IV_BYTES];
            RNG.nextBytes(iv);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, iv)
            );
            cipher.updateAAD(aad(tenantId, objectId));
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            byte[] wrapped = crypto(approvedKeyVersionId)
                .wrapKey(KeyWrapAlgorithm.RSA_OAEP_256, rawDek)
                .getEncryptedKey();

            return new Envelope(
                approvedKeyVersionId, iv, wrapped, ciphertextAndTag
            );
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    public static byte[] decrypt(
            Envelope envelope,
            String authorizedTenantId,
            String authorizedObjectId) throws Exception {

        // IMPORTANT: enforce business authorization outside this method.
        // Validate/allowlist keyVersionId before opening a client.
        byte[] rawDek = crypto(envelope.keyVersionId())
            .unwrapKey(
                KeyWrapAlgorithm.RSA_OAEP_256,
                envelope.wrappedDek()
            ).getKey();

        try {
            SecretKey dek = new SecretKeySpec(rawDek, "AES");
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, envelope.iv())
            );
            cipher.updateAAD(aad(
                authorizedTenantId, authorizedObjectId
            ));
            return cipher.doFinal(envelope.ciphertextAndTag());
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        String approvedId = System.getenv("KEY_VERSIONED_ID");
        if (approvedId == null || approvedId.isBlank()) {
            throw new IllegalStateException("KEY_VERSIONED_ID required");
        }

        byte[] message = "Demo invoice, no PII"
            .getBytes(StandardCharsets.UTF_8);

        Envelope e = encrypt(approvedId, "tenant01", "order123", message);
        byte[] roundtrip = decrypt(e, "tenant01", "order123");

        System.out.println(
            "Envelope validated: " + Arrays.equals(message, roundtrip)
        );

        Arrays.fill(message, (byte) 0);
        Arrays.fill(roundtrip, (byte) 0);
    }
}
~~~

### 10.3. Why This Code Is Still Lab-Grade, Not a Production Library

- `crypto(...)` creates a client/credential per call: production should **reuse** credentials/clients per key version with safe lifecycle/connection pooling.
- The sample does not serialize the envelope to JSON/binary or validate lengths/encodings, IV length, algorithm IDs, key ID allowlists, or untrusted inputs.
- The sample holds all plaintext/ciphertext in RAM: **do not use for large files**.
- In `encrypt`, `finally` attempts to clear `rawDek` even if `wrapKey` fails. Production still needs thorough exception handling, memory-copy mitigation, and client lifecycle management.
- Java/JCE/SDK may retain copies of key/byte arrays; `Arrays.fill` is risk mitigation, not guaranteed complete zeroization.
- The example does not solve **multi-tenant authorization**, rate limiting, content scanning, key permissions, or atomic Blob ↔ DB consistency.
- Nonce and DEK are freshly generated per object. When implementing a **chunked stream**, never copy the same IV/DEK across chunks.
- AAD uses a canonical string in the example; in practice, validate IDs (or use length-prefixed/binary encoding) to prevent ambiguous representations from delimiter characters.
- `Cipher.doFinal` on decrypt fails if the tag is wrong; **never skip tag verification** to try reading plaintext.
- Never build a key ID from an HTTP request. Enforce a vault/key/tenant allowlist before decrypting.

### 10.4. Envelope Structure Stored Alongside the Object

~~~json
{
  "schemaVersion": 1,
  "dataAlgorithm": "AES-256-GCM",
  "keyWrapAlgorithm": "RSA-OAEP-256",
  "kekVersionId": "https://kv-crypto-lab-unique.vault.azure.net/keys/invoice-kek/EXAMPLE_VERSION",
  "ivBase64": "BASE64_12_BYTE_IV",
  "wrappedDekBase64": "BASE64_RSA_WRAPPED_DEK",
  "ciphertextFormat": "ciphertext-followed-by-16-byte-gcm-tag",
  "aadVersion": 1,
  "tenantObjectReference": "opaque-object-id"
}
~~~

This is an **illustrative schema**, not Azure Key Vault API syntax. Base64 markers are placeholders; **never upload a dummy envelope and treat it as encrypted**. Unencrypted fields must be bound via authenticated metadata/AAD or an appropriate integrity check. Although the IV can be public, **IV reuse with the same DEK** is a critical flaw.

### 10.5. When the App Downloads an Invoice

1. Authenticate user/session and verify permission to read the invoice.
2. Look up the object ID in the DB and retrieve the approved ciphertext and envelope.
3. Validate schema, algorithm, vault/key ID/version, size limits, and tenant binding.
4. Call `unwrapKey` on the **stored key version**.
5. Decrypt with AES-GCM using the exact AAD; verify the tag in `doFinal`.
6. On failure, **never return partial plaintext** and never retry without AAD/tag.
7. Return the response over TLS following Content-Disposition/header policies.
8. Log audit metadata (operation, principal, object ID, outcome); never log raw DEK or plaintext.

### 10.6. For Multi-GiB Files

Never call `Cipher#doFinal` over an entire byte array or load the file into RAM. Two better approaches:

- Use a **vetted streaming AEAD** solution with chunk indices, derived IVs, per-chunk tags, an authenticated manifest, and failure cleanup.
- Use **Azure encryption at rest** with CMK if the requirement is only protecting stored data rather than mandating app-level ciphertext.

A homegrown “split AES-GCM into chunks and reuse the same IV” design is **unsafe**. For strict streaming requirements, choose a standardized, security-reviewed library/protocol instead of inventing cryptographic framing.


## 11. Digital Signatures: Sign/Verify Differs from Encrypt/Decrypt

### 11.1. When Signatures Are Needed

An ETL batch exports reconciliation data. The application needs to verify that a **manifest was signed by an authorized system** and has not been altered since issuance.

- **Hash:** condenses data into a digest; a hash alone does not prove who created the data.
- **Sign:** uses an authorized private key/crypto operation to sign the digest under a signature algorithm.
- **Verify:** validates the signature using the corresponding public key.
- **Encrypt:** keeps content confidential; **not** a signature.

### 11.2. Java Sample Signing a SHA-256 Digest with RSA

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.SignatureAlgorithm;
import com.azure.security.keyvault.keys.cryptography.models.SignResult;
import com.azure.security.keyvault.keys.cryptography.models.VerifyResult;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class SignVerifyDemo {
    public static void main(String[] args) throws Exception {
        String keyId = System.getenv("SIGN_KEY_VERSIONED_ID");
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        CryptographyClient crypto =
            new CryptographyClientBuilder()
                .keyIdentifier(keyId)
                .credential(credential)
                .buildClient();

        byte[] payload = "approved-manifest-v1"
            .getBytes(StandardCharsets.UTF_8);

        byte[] digest =
            MessageDigest.getInstance("SHA-256").digest(payload);

        SignResult signature =
            crypto.sign(SignatureAlgorithm.RS256, digest);

        VerifyResult verification = crypto.verify(
            SignatureAlgorithm.RS256,
            digest,
            signature.getSignature()
        );

        System.out.println("Signature valid: " + verification.isValid());
    }
}
~~~

**Note:** `RS256` is the RSA-with-SHA-256 signing algorithm per SDK semantics, not RSA-OAEP encryption. For new designs, evaluate RSA-PSS (`PS256` where supported) or ECDSA per security policy. You must **pin trusted public keys/versions and an appropriate trust chain**—never let a sender pick an arbitrary key, verify with that same key, and call it a trusted signature.

### 11.3. Sign a Manifest, Not Every Byte Over HTTP

For large files, the app can stream-hash to a SHA-256 digest and call `sign` on the digest instead of sending the whole file to Key Vault. The manifest should record:

~~~json
{
  "manifestVersion": 1,
  "objectId": "file-123",
  "sha256": "HEX_SHA256_OF_FILE",
  "signatureAlgorithm": "RS256",
  "signingKeyVersionId": "https://kv-crypto-lab-unique.vault.azure.net/keys/signing-key/EXAMPLE_VERSION",
  "signatureBase64": "BASE64_SIGNATURE"
}
~~~

Define **canonical serialization** of the signed bytes. If signing hashes the file digest while verification hashes a differently formatted JSON string, a signature mismatch does not necessarily mean data tampering.

**A signature proves origin based on possession of the private key**, not that the initial data-generation process had no business logic bugs. Protect the `sign` permission so no unintended service can sign forged documents.

## 12. Rotation, Key-Version Pinning, and Rewrapping Data

### 12.1. Scenario: One KEK Across Three Versions

~~~text
invoice-kek / V1  → wrapped DEK for invoices from Jan–Apr
invoice-kek / V2  → wrapped DEK for invoices from May–Aug
invoice-kek / V3  → new writes from Sep onward
~~~

If a program decrypts all old invoices by calling `getKey("invoice-kek")` and getting V3, DEKs wrapped with V1/V2 **cannot be unwrapped with V3 alone**. Metadata must store the **specific key identifier and version** used.

### 12.2. KEK Rotation Without Changing Payload Ciphertext

For AES-GCM ciphertext already encrypted with a DEK:

1. Read `oldKeyVersionId` and `wrappedDekOld`.
2. Validate the record, operator permissions, and the new key.
3. Call `unwrapKey` using the **old KEK version** to obtain the raw DEK in a trusted environment.
4. Call `wrapKey` using the **new KEK version**.
5. Write `wrappedDekNew` and `newKeyVersionId` into the envelope **atomically/conditionally** per DB/Blob metadata mechanisms.
6. Verify unwrap with the new version and decrypt sample ciphertext.
7. Retain the old KEK version until all records are migrated or retention ends.

**Payload ciphertext and IV can remain unchanged** if the DEK does not change. This is **rewrapping**, not replacing the DEK or re-encrypting all data.

### 12.3. Safe Rewrap Runbook

~~~mermaid
flowchart TD
    A["Read envelope metadata"]
    B["Validate tenant, object and old key ID"]
    C["Unwrap with old KEK version"]
    D["Wrap same DEK with new KEK version"]
    E["Conditional update of envelope"]
    F["Read back + sample decrypt"]
    G{"Validation PASS?"}
    H["Mark rewrapped / record audit"]
    X["Stop / rollback to old metadata"]
    A --> B --> C --> D --> E --> F --> G
    G -->|"Yes"| H
    G -->|"No"| X
~~~

**Subtle pitfall:** Never update a record's metadata to the new key ID **before** the new wrapped DEK is persisted successfully. If updates span multiple objects/DBs, use appropriate transactions/ETags, migration state tracking, and a reconciliation worker. Never delete old key versions while unmigrated records remain.

### 12.4. When the DEK Itself Must Change

Rekeying differs from rewrapping. Changing the DEK requires:

- Decrypting the entire old payload with the old DEK.
- Generating a new DEK/IV.
- Re-encrypting the payload.
- Wrapping the new DEK with the target KEK/version.
- Committing ciphertext + envelope synchronously per design.
- Verifying integrity, retention, and cleanup of old ciphertext.

This consumes far more bandwidth/compute and carries higher outage risk than rewrapping. **If a raw DEK is exposed**, merely rewrapping the old DEK with a new KEK **does not fix** the exposure; you must **re-encrypt with a new DEK** per incident plan.

### 12.5. Crypto-Erasure and Key Deletion

Destroying access to a key can render ciphertext unreadable, but it only qualifies as **crypto-erasure** if the model holds: no remaining copies of the DEK, KEK, backups/versions, or plaintext copies elsewhere. Soft delete/purge protection may preserve recoverability per policy; **never use key deletion as routine business data deletion** without legal and backup review.

### 12.6. Rotating Keys After Compromise

- If a principal with `unwrapKey` is compromised, assume the DEKs/ciphertexts that principal could access are at risk.
- If a raw DEK is exposed, re-encrypt affected objects with a **new DEK**.
- If a signing key is compromised, revoke trust, rotate the key/version, and audit previously issued signatures.
- If a vault key was disabled by mistake without compromise, prioritize recovery/re-enabling with approval rather than creating a new key with the same name.
- Record the incident timeline, authorization scope, audit logs, and verification results before closing the incident.

## 13. Azure Service-Integrated CMK vs. App-Level Envelope Encryption

### 13.1. Two Different Models

**Model A — Customer-managed key (CMK) for service encryption at rest**

~~~text
Java application
  → Azure Blob Storage / Azure SQL / other service
  → Service-side storage encryption
  → Azure Key Vault KEK / identity integration per configuration
~~~

The application typically **does not decrypt every file itself**. The Azure service is configured with a key ID, identity, and permissions to manage encryption at rest, subject to per-service conditions and limits.

**Model B — Application-level envelope encryption**

~~~text
Java application
  → AES-GCM encrypt data before storage
  → Key Vault wraps DEK
  → Blob/DB stores only application ciphertext + envelope
~~~

Data is encrypted **before reaching storage**; the application owns the key-envelope format, integrity, rotation, decryption authorization, and restore workflow.

### 13.2. Comparison

| Criterion | Service-side CMK | App-level envelope |
| --- | --- | --- |
| Who encrypts the payload? | Azure service per integration mechanism | Application/library |
| App code changes | Usually minimal | Significant: crypto format, AAD, streaming |
| Key Vault operations | Performed by service integration | App calls wrap/unwrap |
| Only data owner decrypts? | Depends on service data access/identity | Can enforce decryption separation at app tier |
| Rotation | Follows service key URI/refresh mechanism | App must manage key versions and rewrapping |
| Content search/query | Service may process plaintext per feature | Ciphertext generally cannot be queried directly |
| Auditing | Service/key operations per integration | App-level access + Vault diagnostics |
| Key loss impact | Service may lose access to data | App cannot unwrap DEK |
| Complexity | Relatively lower | Relatively higher |

Do not conclude that CMK **automatically** enforces tenant isolation or prevents Azure resource admins with data-plane permissions from reading contents. CMK does not replace storage/database access controls.

### 13.3. Assigning Permissions to a Service-Managed Identity

Depending on the Azure resource (e.g., Storage with customer-managed keys), the service needs an identity and supported key permissions/roles such as **Key Vault Crypto Service Encryption User** or equivalent. Verify the exact RBAC data actions, Key Vault firewall/Private Endpoint behavior, and key URI/rotation behavior of **each integration**—never grant `Key Vault Administrator` to a service.

### 13.4. When to Use Both Layers

An organization may use **Storage encryption at rest with CMK** while also **encrypting ultra-sensitive content with app-side AES-GCM**. These are two separate layers with distinct key management, cost, and recovery workflows. Deploy both only when clearly justified by threat modeling and compliance; custom crypto increases risk without team review of protocols, key lifecycles, and incident handling.

## 14. Networking, Private Endpoints, and Protecting Key Access

### 14.1. Private Link Does Not Replace Permissions

Key Vault has an official endpoint:

~~~text
https://kv-orders-prod.vault.azure.net/
~~~

When Private Endpoint is enabled, VNet and DNS are configured so this hostname resolves over a private path. Typical Private DNS Zone:

~~~text
privatelink.vaultcore.azure.net
~~~

The application **still uses the standard vault hostname**. Never substitute the raw private IP to bypass DNS, because TLS requires hostname/certificate verification. Never disable certificate validation when errors occur.

### 14.2. Two Independent Conditions

| Question | Control mechanism |
| --- | --- |
| Is the principal allowed to call `unwrapKey` on this key? | Entra identity + Key Vault data-plane RBAC/access model |
| Does the request come from an allowed network/source? | Firewall, Private Endpoint, DNS, routing, trusted services exceptions if any |
| Is the end user allowed to decrypt this object? | Business authorization in the app |
| Do we need proof of who performed the operation? | Audit logs and correlation IDs |

An identity with Crypto User outside the allowed network path can still be blocked. A pod inside a VNet with a Private Endpoint but no data role still gets 403. Never enable public network access `All networks` to fix an RBAC error.

### 14.3. Check DNS/TCP from the Actual Client

Linux:

~~~bash
VAULT_HOST="kv-orders-prod.vault.azure.net"
nslookup "$VAULT_HOST"
nc -vz "$VAULT_HOST" 443
~~~

PowerShell:

~~~powershell
Resolve-DnsName kv-orders-prod.vault.azure.net
Test-NetConnection kv-orders-prod.vault.azure.net -Port 443
~~~

These commands only check DNS/TCP; **they do not verify authorized crypto operations**. Test using the workload's identity in the actual VNet/region, not just from a laptop.

### 14.4. Anti-Misconfiguration Rules

- Never put client secrets in `application.yml`/Docker images.
- Never grant Crypto Officer/Administrator to every application.
- Never share one vault across all tenants/teams if your threat model requires isolation.
- Enable public access/trusted-services exemptions only when policy requires and reviews them.
- Never write key material, plaintext, tokens, or full unredacted requests to telemetry.
- Enforce a vault URL/key allowlist from config; block SSRF-style dynamic key identifiers.
- Use TLS and enforce CA/hostname validation.
- Restrict network egress when a workload only needs specific endpoints.

## 15. Auditing, Monitoring, Quotas, and Cost

### 15.1. What Needs to Be Monitored?

| Signal | Meaning |
| --- | --- |
| Count of encrypt/decrypt/wrap/unwrap/sign/verify calls | Workload usage, cost, and anomalies |
| HTTP 401/403 | Credentials, RBAC, firewall, or policy |
| HTTP 404 | Key/vault/version missing or deleted |
| HTTP 429 | Throttling/quotas or excessive operations |
| HTTP 5xx/timeouts | Transient dependency, network, or service issues |
| p50/p95/p99 duration for `unwrapKey` | Latency impacting download/decryption |
| Key version/rotation events | Ability to decrypt older data |
| Key disabled/deleted/purge attempts | Security incident or unauthorized change |
| Role assignment changes | Widening of crypto permissions |
| Vault network/private endpoint changes | Outage or opened access |
| Audit/diagnostic settings disabled | Loss of visibility |
| Cost per wrapped DEK / per workload | FinOps and caching/routing efficiency |

### 15.2. Azure Monitor and Diagnostic Settings

Use Azure Monitor/Log Analytics to collect Key Vault diagnostic logs per policy. **Azure Activity Log** primarily captures control-plane changes; **Key Vault audit logs** (category/resource-specific per config) capture service-recorded data-plane operations.

Read-only CLI commands:

~~~bash
VAULT_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query id -o tsv)

az monitor diagnostic-settings list \
  --resource "$VAULT_ID" \
  --output json

az monitor metrics list-definitions \
  --resource "$VAULT_ID" \
  --output table
~~~

Do not assume creating a Key Vault automatically sends every crypto operation to Log Analytics: you must **configure diagnostic settings, destination, retention, and IAM**. Metrics/log tables/fields can vary by resource and schema.

### 15.3. Example KQL for Analyzing Key Vault Audits

This example applies **if** the workspace uses the `AzureDiagnostics` table and `AuditEvent` category:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where Category == "AuditEvent"
| summarize Calls = count() by OperationName, ResultType
| order by Calls desc
~~~

With resource-specific tables, look up the **actual table and column names** and adjust KQL accordingly. Zero rows do not prove zero key operations if logging is disabled, pointed to the wrong workspace, or affected by sampling/retention.

### 15.4. Application-Level Telemetry Without Plaintext

A valid trace span might look like:

~~~json
{
  "operation": "keyvault.unwrap_key",
  "environment": "prod",
  "keyAlias": "invoice-kek",
  "keyVersionAlias": "v2026-11",
  "durationMs": 37,
  "status": "success",
  "objectCategory": "invoice",
  "requestId": "opaque-correlation-id"
}
~~~

This is an **illustrative application schema**, not a built-in Key Vault JSON format. Never put raw DEKs, ciphertext, wrapped DEKs, plaintext, request bearer tokens, or sensitive object contents in logs. A key version alias can be used when avoiding exposure of full key URI structure.

### 15.5. Throttling and Retries

Key Vault crypto operations are subject to throughput limits/quotas by SKU, operation type, and service scope. When hitting `429`:

1. Check retry-after/guidance headers if present.
2. Use jittered backoff with **bounded attempts/deadlines**.
3. Avoid multiplicative retries across layers (API gateway × app × SDK).
4. Eliminate unnecessary crypto calls.
5. Review key/region distribution and capacity per policy.
6. Never fall back to a static plain AES key in config to “bypass Key Vault for speed”.

**401/403/404 errors from authorization/key version issues are usually not transient**; do not retry endlessly. When an unwrap fails, never continue returning plaintext or fall back to an unverified key.

### 15.6. What Are the Cost Components?

- Vault SKU, HSM-backed keys/Managed HSM billing if applicable.
- Number of cryptographic operations by type and pricing tier.
- Compute/app latency and concurrency when calling Key Vault frequently.
- Private Endpoints/networking, cross-region data transfer if any.
- Diagnostic logs, Log Analytics ingestion/retention, and alerts.
- Storage for ciphertext, wrapped DEKs, and envelope metadata.
- Key rotation/rewrap jobs and backup/DR testing.
- Audit/compliance staffing if mandated by regulation.

Pricing depends on SKU, region, operation, and date; **never cite placeholder numbers as real Azure pricing**. Use the Azure Pricing Calculator and Cost Management to verify.

### 15.7. Why Envelope Encryption Beats Calling Key Vault Per Chunk

Suppose a 1 GiB file is split into 64,000 chunks of 16 KiB. Calling Key Vault for every chunk generates massive remote crypto operations, spiking latency, cost, and throttling risk.

With envelope encryption, there is typically **one DEK wrap/unwrap per object/session** while bulk crypto runs locally with AES-GCM. However, splitting large files into chunks still requires a **proper chunked AEAD protocol** that never reuses the same nonce with the same DEK.

### 15.8. Caching and Key Usage

- **Public keys/metadata** may be cached when compatible with rotation/version/authorization models.
- Never cache raw DEKs indefinitely in Redis/shared caches to skip unwrapping.
- If short-lived plaintext DEK caching is truly required, enforce threat modeling, TTLs, memory controls, tenant isolation, and auditing.
- Never cache the “latest” key ID forever without picking up rotations.
- Never share a plaintext DEK across unintended tenants/objects just to save calls.


## 16. Contingency Planning, Restore, and Handling Key Loss

### 16.1. Do RPO/RTO of Encrypted Data Depend on Keys?

Suppose Blob Storage holds three replicas of ciphertext, but the **KEK version used to wrap the DEK** was permanently purged. You still have all the ciphertext, yet **cannot decrypt it**.

Therefore, disaster recovery (DR) planning for encrypted data must address jointly:

- **Data RPO:** how much data/transaction loss is tolerable.
- **Service RTO:** how quickly the app must resume serving.
- **Key recoverability:** whether vault/key versions/backups and access remain usable.
- **Envelope recoverability:** whether wrapped DEKs/IV/AAD/format metadata still match the ciphertext.
- **Regional compatibility:** key backup/restore, region, identity, and network constraints per service rules.
- **Retention/legal hold obligations:** never accidentally purge keys while data still requires reading.

**Backing up ciphertext without backing up/recovering keys and matching metadata is insufficient for DR.**

### 16.2. Assets That Must Be Protected Together

| Component | Risk | Mitigation |
| --- | --- | --- |
| Blob ciphertext | Accidental delete, overwrite, region outage | Versioning/soft delete/replication/backup per policy |
| Wrapped DEK | Lost record or corrupted key ID | Transactional metadata store, backups, integrity checks |
| KEK key version | Disabled/deleted/expired/compromised | Rotation runbook, retention, soft delete, purge protection |
| Vault IAM/network | Role revoked, DNS broken | IaC, audited role backups, and break-glass |
| AES IV/AAD schema | Missing nonce, serialization change | Versioned envelope schema, regression tests |
| Application decrypt code | SDK/model compatibility issues | Versioned releases, recovery builds, tests |
| Audit evidence | Unavailable during incident | Diagnostic settings, retention, and delegated access |

### 16.3. Restore Rehearsal

A restore drill must not stop at “Key Vault was recreated”; it must:

1. Select a **test encrypted object** and its envelope with a specific key version.
2. Confirm vault/key availability or authorized backup/restore steps.
3. Restore ciphertext and envelope into an isolated lab environment.
4. Restore/configure key access, identity, and networking appropriately.
5. Run `unwrapKey` and AES-GCM decryption, verifying tag/AAD.
6. Verify checksum, business object ID, and expected plaintext.
7. Measure actual RTO and record every dependency.
8. Declare PASS only when **data is genuinely readable**, not merely because files appear in Storage.

### 16.4. Purge/Key Compromise Incidents Have Different Priorities

- **Key disabled by mistake:** obtain approval to re-enable, verify version/path, audit, and find root cause.
- **Key soft-deleted:** if within the recovery window with proper permissions, follow the recovery procedure—never create a new key with the same name hoping it will decrypt old data.
- **Key purged or retention expired:** recovery may be impossible; evaluate valid backups/restores and incident impact without promising guaranteed recovery.
- **Raw DEK exposed:** rotating the KEK **is insufficient**; re-encrypt affected ciphertext with a new DEK.
- **Unwrap principal compromised:** isolate/revoke permissions, scope accessed ciphertexts/envelopes, and execute incident response.
- **Signing private key compromised:** rotate trust anchors and audit past signatures rather than just rotating the active key.

## 17. Key Vault Diagnostic Runbook

### 17.1. Error and First-Action Table

| Symptom | Possible Cause | First Action |
| --- | --- | --- |
| `401 Unauthorized` | Invalid/expired OAuth token, credential config | Check token audience/identity and managed identity |
| `403 Forbidden` | Missing `unwrapKey`/RBAC, firewall, or policy | Check principal, role, error details, network |
| `404 Not Found` | Key/version missing, deleted, or wrong vault | Cross-check versioned key ID and vault |
| `400 Bad Request` | Unsupported algorithm/key type, plaintext too long | Check RSA/EC, OAEP size limits, SDK options |
| `429 Too Many Requests` | Key Vault throttling/quota | Bounded backoff, metrics, reduce calls |
| `5xx / timeout` | Service/network/transient failure | Retry with deadline, check service health/status |
| `UnknownHost / DNS failure` | Wrong Private DNS/forwarding/VNet link | Resolve vault FQDN from the actual workload |
| TLS handshake error | Hostname/CA/network interception | Fix DNS/trust; never disable TLS |
| `Unwrap` fails after rotation | Key version changed/disabled/deleted or wrong key ID | Read envelope `kekVersionId`, restore access to that version |
| AES-GCM bad tag | Wrong or tampered ciphertext/IV/AAD/DEK | Block plaintext, investigate integrity/metadata |
| Java SDK builds client but crypto fails | Wrong role, network, algorithm, or key operation permissions | Trace request/status; do not use admin keys |
| Key created but private material unexportable | Key Vault/HSM protection boundary | Use crypto APIs; this is expected behavior, not a bug |
| Logs empty while app calls vault | Wrong diagnostic settings/workspace | Verify log pipeline and target tables |
| Cost and latency spike | Crypto calls per chunk, retry storm | Measure calls/request, optimize envelope pattern |
| Cannot purge immediately | Purge protection/retention policy | Do not bypass; comply with retention |

### 17.2. Step 1 — Capture Request Details and Blast Radius

Record:

~~~text
timestamp_utc
subscription_id / resource_group
vault_alias / key_alias / key_version
application_release / sdk_version
managed_identity_principal_id
operation = encrypt | decrypt | wrap | unwrap | sign | verify
http_status / service_error_code
request_correlation_id
tenant_scope / object_category (sanitized)
~~~

**Never record:** raw keys, DEKs, tokens, confidential ciphertext, plaintext, user secrets, key backup bytes, or private data in public incident tickets.

### 17.3. Step 2 — Verify DNS and Permissions

~~~bash
az account show \
  --query "{subscriptionId:id,tenantId:tenantId}" \
  --output json

az keyvault show \
  --name "$VAULT" \
  --output json

az keyvault key show \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output json
~~~

If your desktop CLI works while an AKS pod fails, **never assume the workload shares the same identity, network route, or DNS**. Inspect the pod's managed identity object ID and token source, then its role assignments.

### 17.4. Step 3 — Classify Authorization at the Right Layer

- **401:** invalid credential/token/audience or unauthenticated request.
- **403:** could be data-role permissions, Key Vault firewall, network access, key attributes, or access policy model. Read service error details and audit logs.
- **404:** key/version/vault path does not exist or was deleted/changed; never substitute the latest version automatically.
- **400:** RSA payload too large, incompatible algorithm (e.g., EC key with RSA OAEP), or invalid key operations.

Some security configurations intentionally hide existence details; evaluate error codes alongside vault diagnostics rather than status code alone.

### 17.5. Step 4 — Check the Key Version Used by the Envelope

Read the **version recorded in ciphertext metadata**, rather than calling `getKey(latest)` when investigating decryption:

~~~text
Envelope:
  keyId: invoice-kek/version-V1
Vault:
  invoice-kek: V1, V2, V3
Application:
  latest key lookup returns V3

Correct: decrypt using V1; new encrypt may use V3.
Incorrect: attempt to unwrap old DEK with V3.
~~~

If V1 is disabled/expired, follow runbooks/approvals to restore access for old data or run a planned rewrap; never disable policies arbitrarily in production.

### 17.6. Step 5 — Check AES-GCM Integrity

If `Cipher.doFinal` throws a tag verification error:

1. **Never return partial plaintext** to the user.
2. Compare ciphertext hash/size and envelope schema version.
3. Verify IV length, tag format, and canonical AAD encoding.
4. Confirm tenant/object IDs at decrypt match those used at encrypt.
5. Check wrapped DEK and version ID validity.
6. Check whether a migration/serialization/record-splitting bug corrupted data.
7. If tampering is suspected, treat it as an integrity/security incident and preserve evidence.

Never “fix” it by removing `GCMParameterSpec`, switching to ECB, hardcoding IVs, or dropping AAD.

### 17.7. Step 6 — Evaluate 429s, Timeouts, and Retries

Key Vault is a network dependency; HSM operations in particular can have different throughput/latency than software keys. Check:

- Crypto calls per user request.
- Retry counts in both the SDK and application layer.
- Deadlines and backoff.
- Number of vaults/keys, regions, and actual quotas.
- Is an active key rotation increasing call volume?
- Is the app calling unwrap per chunk instead of once per object/session?
- CPU/heap and TLS connection reuse.

Never fall back to a static AES master key in config to bypass Key Vault after hitting 429s.

### 17.8. Step 7 — Post-Incident Verification

- Key versions are valid and meet least-privilege permissions.
- Old/new envelopes decrypt cleanly or have a documented migration decision.
- AES-GCM tags and business authorization PASS.
- 401/403/429/5xx rates have returned within acceptable thresholds.
- Rotation/backup/soft delete/purge protection remain intact.
- No plaintext DEKs or tokens appear in logs.
- Auditing and alerting are active, and the business owner confirms recovery.
- Cost/throughput align with budget.

### 17.9. Break-Glass Access

During a key-access outage, never grant permanent `Key Vault Administrator` to all SREs. Use a break-glass process featuring:

- Independent identities activated only during incidents with multi-step approval.
- `Just-in-time` / PIM access where available.
- Clear vault/key scope and short duration.
- Operation auditing, post-incident review, and timely revocation.
- Negative tests confirming app runtimes do not retain admin rights post-incident.


## 18. Lab: Creating a KEK and Encrypting a Sample Invoice

### 18.1. Objectives and Scope

This lab uses **synthetic data only**, never real personal records or real orders:

~~~text
Subscription:     Approved Azure lab
Resource group:   rg-crypto-lab
Key Vault:        kv-crypto-lab-unique
Key name:         invoice-kek
Key type:         RSA 3072 (software key for demo)
Identity:         local Azure CLI identity / lab managed identity
Crypto SDK:       azure-security-keyvault-keys
Java version:     17+
Payload:          "Demo invoice, no PII"
Expected result:  valid decrypt and GCM rejects tampering
~~~

If you lack a subscription/permissions, complete the design exercise on paper using the questions below. **You are not required to provision billable resources to learn this lesson.**

### 18.2. Practice Steps

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | `az account show` to verify subscription/tenant | Correct context, not production |
| 2 | `az keyvault show` to verify RBAC model, region, recovery | Lab vault exists, policy matches |
| 3 | `az keyvault key list`/`show` | Key name/version existence verified |
| 4 | Operator creates key if authorized | Valid versioned RSA key ID |
| 5 | Security admin assigns minimal Crypto role | Actual principal granted permission |
| 6 | Set `KEY_VERSIONED_ID` | Contains exact vault, key, and version |
| 7 | Run Java small-payload encrypt/decrypt | RSA-OAEP-256 round-trip PASS |
| 8 | Run Java AES key wrap/unwrap | DEK bytes match |
| 9 | Run EnvelopeCryptoDemo | Decrypted plaintext matches original |
| 10 | Flip 1 byte of ciphertext, keep old tag | AES-GCM decrypt FAILS |
| 11 | Keep ciphertext, alter tenant/object AAD | AES-GCM decrypt FAILS |
| 12 | Create a new KEK version in lab with approval | Both old/new key IDs recorded |
| 13 | Decrypt old envelope using old version | PASS |
| 14 | Simulate rewrapping DEK to new version | Old payload unchanged, new wrapped DEK |
| 15 | Re-run decrypt with new key version | PASS |
| 16 | Measure latency/timeouts and audit logs | Request IDs present, no plaintext logged |
| 17 | Test principal with only Key Vault Reader | Cannot unwrap/decrypt |
| 18 | Test Private Endpoint/firewall if lab supports it | Network errors properly classified |
| 19 | Inspect crypto call count and cost estimate | Not called per chunk |
| 20 | Clean up per policy and inventory | Do not purge keys tied to readable data |

Never run disable/delete/purge directly to induce failure tests on a shared vault.

### 18.3. Negative Test with AES-GCM

Example test logic:

~~~java
EnvelopeCryptoDemo.Envelope original =
    EnvelopeCryptoDemo.encrypt(
        approvedVersionedKeyId, "tenant01", "order123",
        "Invoice demo".getBytes(java.nio.charset.StandardCharsets.UTF_8)
    );

// Create a copy to test integrity failure.
byte[] tampered = original.ciphertextAndTag().clone();
tampered[0] ^= 1;

EnvelopeCryptoDemo.Envelope damaged =
    new EnvelopeCryptoDemo.Envelope(
        original.keyVersionId(),
        original.iv().clone(),
        original.wrappedDek().clone(),
        tampered
    );

boolean rejected = false;
try {
    EnvelopeCryptoDemo.decrypt(damaged, "tenant01", "order123");
} catch (javax.crypto.AEADBadTagException expected) {
    rejected = true;
}
if (!rejected) {
    throw new IllegalStateException("Tampered ciphertext accepted!");
}
~~~

This is a **test snippet inside a class/method that already has the variables and permissions**; it is not a standalone program. Some JCE providers may report tag verification failures using a different exception type depending on implementation; for portable tests, check API/provider behavior and never catch all errors and claim “tamper detected” if the error came from networking or configuration.

### 18.4. Positive and Negative Permission Cases

| Principal | Expected Permissions | Test |
| --- | --- | --- |
| Provisioner | Create/rotate keys at scope | Create key in lab, unused by runtime |
| Encrypt-only workload | Encrypt/wrap per policy | Wrap succeeds; unwrap **denied** if custom role supports it |
| Decrypt workload | Unwrap/decrypt per policy | Decrypts authorized object |
| Metadata reader | Read key metadata only | `getKey` may PASS, `unwrapKey` DENIED |
| Incident operator | Temporary approved access | Restore/rotation with audit |
| End user | No direct Key Vault access | Only calls business-authorized APIs |
| External attacker | No private route/credential | Connection fails or blocked |
| Key disabled/deleted | No crypto operations allowed | Fails per key state; data unreadable |

**Test with the real identity/credential.** If every test runs as `Key Vault Administrator`, a successful unwrap proves nothing about least privilege.

### 18.5. Cost and Latency Calculation Exercise

Suppose there are 50,000 file uploads/day. If the design calls Key Vault **1 wrap per file**, theoretical wrap operations:

\[
50{,}000\ \text{wrap calls/day}.
\]

If downloads average 20,000/day and each download unwraps once:

\[
50{,}000 + 20{,}000 = 70{,}000\ \text{crypto operations/day}.
\]

These are **hypothetical operation counts**, not an invoice. Retries, rewrap jobs, signature verifications, or key metadata GETs change actual operation totals. Use the Azure Pricing Calculator by SKU/region/operation to estimate rather than assigning fixed USD rates.

### 18.6. Architecture Selection Exercise

**Requirement A:** PDFs only need encryption at rest in Storage, with no requirement for application-layer ciphertext.

**Choice:** Evaluate Storage encryption and CMK Key Vault integration where appropriate instead of building custom AES-GCM envelope serialization.

**Requirement B:** Sensitive records must be encrypted before storage, with per-object DEKs and key/tenant separation.

**Choice:** App-level envelope encryption, authenticated AES-GCM, Key Vault KEK wrapping, versioned key IDs, and strict authorization, plus evaluating vetted streaming libraries/protocols.

**Requirement C:** Must verify that a file was issued by an internal system without needing to hide its contents.

**Choice:** Digital signature/verify with a signing key and signed manifest; do not use encryption as a substitute for signatures.

## 19. Real-World Scenarios and Thinking Exercises

### 19.1. Scenario A — Rotation Breaks Decryption on 10% of Old Data

The new app only calls `getKey("invoice-kek")` to fetch the latest version and tries to unwrap all documents.

**Analysis:** Old records hold DEKs wrapped under earlier versions. **Fix:** store and read `kekVersionId` per envelope, keep old versions valid or run controlled rewrapping; never create a new KEK to try decrypting.

### 19.2. Scenario B — A Developer Has Reader on the Vault but Cannot Read Plaintext Secrets

**Analysis:** Key Vault Reader mainly views metadata per role and does not read secret values or unwrap keys. Azure management Reader is not Key Vault data-plane Reader either. Verify the exact role, authorization model, scope, and network rather than granting Administrator just to test.

### 19.3. Scenario C — Blob Store Uses AES-GCM Encryption Yet Still Leaks Data

The API does not check object ownership and uses a managed identity with `unwrapKey` across all KEKs. User A guesses User B's object ID, and the API returns plaintext.

**Analysis:** Encryption **does not replace business authorization**. Enforce tenant/object ownership checks before fetching/unwrapping, narrow key access scope, and audit. If real leakage occurred, handle it as a security incident.

### 19.4. Scenario D — Rewrapping After a Raw DEK Was Exposed

The operations team assumed rewrapping the old DEK with a new key resolved the compromise.

**Analysis:** Incorrect; the attacker still knows the DEK. **Fix:** re-encrypt affected payloads with a fresh DEK/IV, wrap with a valid KEK, and handle old copies/retention per the incident runbook.

### 19.5. Scenario E — Reusing the Same 12-Byte IV Across Every Chunk of a File

The app splits a file into chunks, using a fixed DEK and identical IV for every chunk.

**Analysis:** **Severe vulnerability in AES-GCM.** Never do this; use a standardized streaming AEAD design with a unique nonce per key/chunk and manifest authentication, or a vetted library.

### 19.6. Scenario F — Key Vault Has a Private Endpoint, Yet Java Still Times Out

**Analysis:** DNS/routing/Private DNS Zone, network policy, or TLS hostname may be wrong. Check `privatelink.vaultcore.azure.net`, VNet links, and connectivity from the actual workload; never put a raw IP in the vault URL.

### 19.7. Scenario G — Key Vault Costs Spike After an Upload Refactor

The old pipeline wrapped 1 DEK/file; the new version calls remote RSA encrypt for every 4 KiB chunk.

**Analysis:** Remote crypto operations surged, risking quota, latency, and cost issues. **Fix:** return to the envelope model with local AES-GCM, while still designing secure chunk encryption for streaming.

### 19.8. Scenario H — Cannot Permanently Delete a Key Immediately

The vault has purge protection enabled, and an operator wants to purge a key to clean up an environment.

**Analysis:** Purge protection is a retention safeguard, not an error to bypass. Follow resource/lab policies and wait out retention; never force deletion if ciphertext still depends on it.

### 19.9. Scenario I — A Valid Digital Signature Still Has Wrong Data

A manifest was signed by an authorized app, yet the monetary amount was miscalculated due to a bug.

**Analysis:** A signature proves signer origin and integrity under the trust model; **it does not guarantee business correctness**. Separate validation and data-correction workflows are required.

### 19.10. Scenario J — Key Vault Backup Restored, Yet Files Still Cannot Be Read

**Analysis:** Check wrapped DEK, exact versioned key ID, IV, AAD schema, ciphertext tag, encryption algorithm, IAM/network, and app compatibility. Never treat a successful key backup restore as complete DR.

### 19.11. Scenario K — HSM-Backed Key Cannot Export a PEM Private Key

**Analysis:** That is the purpose of the HSM protection boundary, not a bug. Use crypto operations/managed lifecycles; if migration is required, inspect supported backup/restore/service-specific models and restrictions.

### 19.12. Scenario L — Entra Identity Has Crypto User Yet Still Gets 403

**Analysis:** Possible causes include wrong principal object ID, unpropagated role, vault in access-policy mode, restricted key operations, Private Endpoint/firewall denial, or the app using a different identity. Gather error codes/requests and inspect each layer before granting broader permissions.

## 20. Production Design Checklist

### 20.1. IAM and Data

- [ ] Business data classification exists with a clear CMK vs. app-level encryption decision.
- [ ] KEK/DEK hierarchy is documented in the architecture; keys are not confused with secrets.
- [ ] Permitted key operations match the RSA/EC/key type and policy.
- [ ] Managed identity/workload identity is configured; no hardcoded client secrets.
- [ ] Azure RBAC data roles use least-privilege scope; runtimes cannot rotate/purge.
- [ ] Business authorization protects tenant/object ownership before unwrapping.
- [ ] Raw DEKs, plaintext, tokens, and sensitive signed URLs never appear in logs.
- [ ] Every ciphertext/envelope stores versioned KEK ID, algorithm, and AAD schema.
- [ ] Negative tests exist to block unauthorized unwrap/decrypt.
- [ ] AES-GCM uses fresh DEKs/unique IVs and enforces tag verification.
- [ ] No AES-ECB or nonce reuse; large files are never encrypted directly with RSA.

### 20.2. Key Lifecycle and Recoverability

- [ ] Every key has an owner, purpose, crypto policy, and rotation schedule.
- [ ] Active versions for new writes are distinguished from old versions for reads.
- [ ] Rotation/rewrap procedures include testing, retries, reconciliation, and rollback.
- [ ] Soft delete/purge protection/retention meet compliance requirements.
- [ ] Key backups/DR are tested per SKU, region, and restrictions.
- [ ] Restore drills actually decrypt a test object.
- [ ] A re-encryption plan exists for raw DEK/KEK compromise.
- [ ] Old versions are never disabled/purged before migration and sign-off complete.
- [ ] Break-glass procedures and auditing of privileged access are in place.

### 20.3. Networking, Monitoring, and FinOps

- [ ] Vault FQDN/TLS and Private Endpoint/Private DNS are verified working.
- [ ] Public access/trusted-services exceptions exist only when approved.
- [ ] Diagnostics/Log Analytics/Azure Monitor are enabled with proper categories/destinations.
- [ ] 401/403/404/429/5xx and key-state changes have alerts/runbooks.
- [ ] Application includes trace correlation without logging sensitive payloads.
- [ ] Retries/backoff/deadlines/circuit breakers have clear bounds.
- [ ] Key Vault is not called per data chunk unintentionally.
- [ ] Crypto operation p95/p99 latency and costs are monitored.
- [ ] IAM/network/key changes are reviewed and have owners.
- [ ] Separate sandbox/lab exists; destructive tests never run in production.


## 21. Self-Check Questions

**Q1.** What is the core difference between an Azure Key Vault Key and a Secret?

**Answer:** A Key supports key material management and cryptographic operations per service/key type; a Secret stores a confidential value that an authorized principal can read in plaintext. Use Keys to keep a KEK inside Key Vault's boundary instead of storing a master key in a Secret and distributing it to apps.

**Q2.** Are Key Vault Standard, Premium, and Managed HSM the same?

**Answer:** No. Standard provides software-protected keys, Premium supports HSM-backed key options per features, and Managed HSM is a dedicated HSM service with distinct administration, backup, and billing. Verify actual SKUs and key types.

**Q3.** Why is RSA-OAEP-256 unsuitable for encrypting a 100 MiB file?

**Answer:** RSA-OAEP has a small plaintext limit determined by modulus/padding, and remote operations incur cost and latency. Use AES-GCM for bulk encryption and Key Vault to wrap the DEK.

**Q4.** How many plaintext bytes at most can RSA-2048 + OAEP-SHA256 encrypt?

**Answer:** 256 - 2×32 - 2 = **190 bytes** per RSA-OAEP bounds, with the proper key and algorithm.

**Q5.** What is a DEK, and how does it differ from a KEK?

**Answer:** A DEK is the symmetric key that encrypts data; a KEK protects the DEK. In this lesson, the DEK is a per-object AES-256 key and the KEK is an RSA key version kept in Key Vault.

**Q6.** Is a wrapped DEK the file's ciphertext?

**Answer:** No. The wrapped DEK is the data key protected by the KEK; the file ciphertext is the AES-GCM output over the plaintext.

**Q7.** Why is a distinct IV/nonce needed for each AES-GCM encryption with the same DEK?

**Answer:** Reusing a GCM nonce with the same key severely breaks confidentiality and integrity. In the example, each object uses a new DEK and a random 12-byte IV.

**Q8.** What is AAD used for?

**Answer:** Additional Authenticated Data is not encrypted but is authenticated, binding ciphertext to tenant/object IDs and schema versions. Decryption must reconstruct the exact AAD.

**Q9.** Should an AES-GCM tag error ever be ignored to recover plaintext?

**Answer:** No. It indicates a mismatch or tampering with data, key, IV, or AAD; always fail closed and investigate.

**Q10.** Does a Blob ETag/version replace the versioned key ID?

**Answer:** No. A Blob ETag/version tracks the data object's version; the key version ID identifies the actual KEK used to wrap the DEK. Both metadata items must be managed independently.

**Q11.** When a Key Vault key rotates from V1 to V2, can old ciphertext automatically use V2?

**Answer:** No. Old DEKs wrapped with V1 must be unwrapped with V1, or explicitly rewrapped to V2 via a controlled process.

**Q12.** Does rewrapping require re-encrypting the entire file?

**Answer:** Not necessarily. Rewrapping changes the KEK wrapping layer around the DEK while leaving the AES-GCM payload ciphertext untouched.

**Q13.** If a raw DEK is exposed, is rewrapping with a new KEK secure enough?

**Answer:** No. An attacker still holds the exposed DEK; you must re-encrypt payloads with a fresh DEK and execute incident response.

**Q14.** Why must old key versions be retained during the retention period?

**Answer:** To unwrap/decrypt legacy data and backups/historical objects still referencing that version until rewrap/re-encryption completes or valid retention expires.

**Q15.** Can an HSM-backed key export a plaintext private key via `getKey`?

**Answer:** Not like reading plaintext from a secret. Key Vault/HSM protects the private key inside its boundary, exposing permitted crypto operations instead of handing out the private key freely.

**Q16.** Does `Key Vault Reader` allow unwrapping a DEK?

**Answer:** No. Reader primarily reads metadata; crypto operations require appropriate data-plane permissions/roles.

**Q17.** Is an Azure resource group Contributor automatically a Key Vault Crypto User?

**Answer:** Not directly. However, control-plane/IAM/access-policy management rights may create indirect escalation paths depending on configuration, so review effective privileges.

**Q18.** If a vault uses legacy access policies, does an Azure RBAC role assignment automatically allow unwrapping?

**Answer:** Never assume so. The active authorization model determines how data-plane permissions apply; inspect it and plan migration.

**Q19.** Why is a managed identity better than a hardcoded client secret?

**Answer:** It reduces storing and transmitting static secrets in code and enables governance via Entra ID/RBAC; you must still protect the identity, scope, and network.

**Q20.** If a managed identity has Crypto User but Key Vault private DNS is wrong, will crypto calls succeed?

**Answer:** Likely not. RBAC and networking/TLS are independent layers; verify Private Endpoint/DNS/routing from the workload.

**Q21.** Does a Private Endpoint replace end-user authorization?

**Answer:** No. It only controls the network path; the Java API must still validate tenant/object ownership before decrypting.

**Q22.** How do `Sign` and `Encrypt` differ?

**Answer:** Sign produces a digital signature to verify integrity/signer origin per a trust model; Encrypt keeps content confidential. A signature does not encrypt plaintext.

**Q23.** Why sign a large file's digest instead of sending the whole file to Key Vault sign?

**Answer:** The Sign API operates on digests per algorithm; the app can stream-hash locally to minimize network traffic using a canonical signing protocol.

**Q24.** If a KEK is deleted and a new key is created with the same name, will old data decrypt automatically?

**Answer:** No. Having the same key name does not mean having the same private key material/version; you must recover/restore the original key per service capabilities.

**Q25.** Do soft delete and purge protection guarantee ciphertext can be recovered?

**Answer:** They protect key recovery within specific conditions and retention limits, but you still need data, envelopes, IVs, AAD, versions, app compatibility, and IAM/networking to decrypt.

**Q26.** Is Azure Blob Storage CMK integration the same as an app encrypting files with AES-GCM?

**Answer:** No. With CMK, the Azure service handles encryption at rest per integration; app-level envelope encryption encrypts data before it reaches storage and carries separate operational responsibilities.

**Q27.** Should Key Vault Administrator be granted to an app that only needs to wrap DEKs?

**Answer:** No. Apply least privilege—evaluate Key Vault Crypto User or custom permissions/identity separation per policy.

**Q28.** Why avoid calling Key Vault encrypt for every 4 KiB chunk?

**Answer:** It multiplies remote operations, latency, cost/throttling, and invites flawed crypto framing. Use local AES-GCM with a vetted chunked AEAD scheme when streaming is needed.

**Q29.** What should be checked when receiving HTTP 403 from Key Vault?

**Answer:** Actual principal, role/scope, authorization model, key operations/attributes, firewall/private endpoint/DNS, and service error details—without granting Administrator.

**Q30.** Why must restores be tested with an actual decryption?

**Answer:** Restoring a key object or ciphertext alone is insufficient; you must prove the app can unwrap the DEK at the right version and verify the AES-GCM tag/AAD on the recovered data.

## 22. Common Glossary

| Term | Meaning |
| --- | --- |
| **Key Vault** | Service managing keys, secrets, and certificates with identity/network controls |
| **KEK** | Key Encryption Key — key used to protect a DEK |
| **DEK** | Data Encryption Key — key used to encrypt payloads |
| **Key version** | Specific version of key material and attributes managed by the vault |
| **Wrap/unwrap** | Encrypting/decrypting a symmetric key using a key wrapping algorithm |
| **RSA-OAEP-256** | RSA encryption/wrapping with OAEP-SHA256 |
| **AES-256-GCM** | Symmetric authenticated encryption using a 256-bit DEK |
| **IV/nonce** | Unique value per key/operation; GCM must never reuse it with the same DEK |
| **AAD** | Additional Authenticated Data; checks integrity of associated metadata |
| **Authentication tag** | Value authenticating AEAD output; mismatch must fail |
| **HSM** | Hardware Security Module, hardware protection boundary per configuration |
| **Entra ID** | Identity service authenticating users and workloads |
| **Key Vault RBAC** | Azure data-plane permissions assigned by role and scope |
| **Access policy** | Legacy Key Vault authorization model using permission entries |
| **Managed identity** | Azure resource/workload identity using tokens instead of static secrets |
| **CMK** | Customer-Managed Key integrated with service encryption or custom workloads |
| **Soft delete** | Retains deleted objects for a recovery window |
| **Purge protection** | Prevents permanent deletion before retention ends per policy |
| **Rewrap** | Changing the KEK protecting a DEK while leaving payload ciphertext unchanged if DEK is unchanged |
| **Re-encrypt** | Re-encrypting data with a new DEK/IV or algorithm per migration |
| **RPO/RTO** | Tolerable data loss / target recovery time |
| **Zeroization** | Effort to clear key material from memory; the JVM does not always guarantee clearing all copies |

## Key Takeaways

- **Key Vault Keys, Secrets, and Certificates are distinct**; when you need to keep a private KEK inside the service boundary and invoke crypto operations, use Key Vault Keys instead of distributing a plaintext master secret.
- **RSA-OAEP-256 encrypts only small payloads**; large files should use AES-GCM locally while Key Vault **wraps/unwraps the DEK**.
- **AES-GCM requires never reusing an IV/nonce with the same DEK**, validating tags and AAD properly, and never inventing unauthenticated chunked protocols.
- **Store the versioned key ID in the envelope.** Rotating to a new version does not automatically convert old wrapped DEKs into new wrapped DEKs.
- **Rewrapping a DEK differs from re-encrypting the payload**; if a raw DEK is compromised, rewrapping alone does not remediate the compromise.
- **Key Vault RBAC, managed identity, Private Endpoint, TLS, and business authorization** address separate security layers; never grant crypto admin rights to runtimes.
- **Soft delete, purge protection, and restore drills** must ensure key versions remain available for all data still within retention.
- **Service-side CMK differs from app-level envelope encryption.** Choose based on threat model and operational capability, avoiding unnecessary custom cryptography.
- **Auditing, metrics, bounded retries, crypto call costs, rotation runbooks, and rollbacks** are mandatory parts of running Key Vault in production.

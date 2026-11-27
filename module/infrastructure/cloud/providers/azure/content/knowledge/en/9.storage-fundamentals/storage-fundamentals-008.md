# Encryption, Encryption Scopes, and Customer-Managed Keys

When an application writes invoices, HR records, or backups to Azure Storage, the security question is not just "who is allowed to read the file?" Enterprises also want to know **where the data is encrypted, who controls the keys, whether keys can be separated per data group, and what happens if a key becomes unusable**. Azure Storage provides default server-side encryption (SSE), **encryption scope** options for blob data, and the ability to use **customer-managed keys (CMK)** stored in Azure Key Vault or Azure Key Vault Managed HSM depending on supported configurations.

This lesson belongs to the **Azure Storage Fundamentals** chapter of the `CLOUD_PROVIDERS_AZURE` module. In this module, you explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data; you also learn how to deploy, monitor, secure, and control costs for an Azure application architecture. Here, the focus is organizing encryption policies to both protect stored data and avoid losing data accessibility due to key misconfiguration.

## 1. What Should You Be Able to Do After This Lesson?

- Explain **encryption at rest**, **encryption in transit**, and **client-side encryption**.
- Understand Azure Storage's default server-side encryption and distinguish **Microsoft-managed keys (MMK)** from **customer-managed keys (CMK)**.
- Describe **envelope encryption**, encrypted data, and keys wrapping data keys.
- Distinguish **storage-account-level** encryption policies from **blob/container-level encryption scopes**.
- Design data separation by encryption scope and select key policies for each scope.
- Understand the role of **managed identities**, Azure Key Vault/Managed HSM, key permissions, rotation, and recoverability.
- Inspect configuration via the Azure Portal or Azure CLI and recognize common causes when blob reads/writes fail.
- Select options aligned with security, compliance, operational, and cost requirements.

## 2. Distinguishing Three Encryption Protection Layers

| Layer | When Is Data Protected? | Example in Azure | Limit to Remember |
|---|---|---|---|
| **Encryption at rest** | While data is stored by Azure Storage on storage media. | Azure Storage Service Encryption (SSE). | Callers with valid API access can still read data decrypted by the service. |
| **Encryption in transit** | While data moves between client and service or across network components. | HTTPS/TLS when an app calls Blob Storage. | Does not replace encryption of data written to disk. |
| **Client-side encryption** | The app encrypts data before sending it to Azure. | SDK/app manages encryption and keys on the client side. | Increases responsibility for key management, SDK compatibility, and data processing. |

Suppose an accounting system uploads `invoice.pdf`:

1. The application uses **HTTPS** to transmit the file to Blob Storage.
2. Azure Storage receives the file and encrypts the data **at rest** before persisting via SSE.
3. When an authorized client downloads the file, the service decrypts it server-side and returns the content over HTTPS.
4. If data must stay encrypted even when the Storage API returns results, the app can apply **client-side encryption** and manage the corresponding keys itself.

**Encryption does not replace authorization.** An actor with valid write/delete permissions can still delete or overwrite data even when data at rest is encrypted. Therefore, you still need Microsoft Entra ID, Azure RBAC, data permissions, private networking, soft delete, versioning/immutability, and governance controls as required.

### Encryption at Rest Does Not Mean "Only the Key Holder Can Read the Blob"

When Azure Storage manages encryption and decryption, users permitted to read the blob receive decrypted data from the service. This holds true whether the mechanism uses MMK or CMK. CMK strengthens customer **control over key lifecycle and usage policies**—it does not replace authorization decisions for reading blobs.

## 3. Default Azure Storage Service Encryption (SSE)

Azure Storage automatically encrypts data **at rest** for supported storage accounts; SSE is enabled by default and is not a toggle you "turn on later" per ordinary blob. The service uses strong encryption, commonly **AES-256**, while managing encryption/decryption within the storage infrastructure.

One way to visualize the storage flow:

```text
Application
  │ Uploads data over HTTPS/TLS
  ▼
Azure Storage API ── checks access permissions ──> valid request?
  │
  ▼
Storage Service Encryption
  │ Uses service-managed data key
  ▼
Encrypted data is persisted at the storage layer
```

Benefits:

- Applications do not need to encrypt data prior to upload to benefit from SSE.
- Apps reading/writing blobs normally require no protocol changes when switching between MMK and CMK.
- Encryption executes within the service, reducing development burden on app teams.
- Key policies or encryption scopes can be layered on when tighter control is needed.

### Which Services Support SSE?

Azure Storage includes services such as **Blob Storage, Azure Files, Queue Storage, and Table Storage**. Default SSE applies to stored data; however, **support for CMK and encryption scopes is not uniform across all services or storage account kinds**.

Specifically, **encryption scope** is a feature tied to **Blob Storage** data (including supported Azure Data Lake Storage Gen2 scenarios). Do not treat it as a per-queue or per-entity key selector for Azure Queue or Azure Table. For account-level CMK on Queue/Table or specialized setups, verify features enabled at account creation and current limits of the account kind.

## 4. Microsoft-Managed Keys vs. Customer-Managed Keys

In SSE, distinguish **who manages the key used to protect data encryption keys**.

| Property | Microsoft-Managed Keys (MMK) | Customer-Managed Keys (CMK) |
|---|---|---|
| Wrapping key manager | Microsoft/Azure Storage. | Customer controls the key in Key Vault or Managed HSM in supported models. |
| Initial setup | Usually default. | Requires key vault/HSM, key, identity, permissions, and storage setup. |
| Key rotation | Managed by Azure per service mechanics. | Customer defines lifecycle and rotation policies. |
| Key revocation capability | Not a direct customer operation on platform keys. | Can block the service from using the key; severely impacts data accessibility. |
| Cost and operations | Minimal key management configuration. | Adds responsibility for vault/HSM, permissions, monitoring, recovery, and key transactions. |
| When to use | General data without self-managed key mandates. | Audit regulations, security policies, or independent key management mandates. |

**CMK does not mean Azure Storage stops performing encryption.** Azure Storage remains the component encrypting/decrypting data, but the service must use the customer-managed key to protect the corresponding data encryption keys.

### Envelope Encryption: "A Key Wrapping a Key"

A helpful mental model:

- **Data Encryption Key (DEK):** the data key used to encrypt the actual data.
- **Key Encryption Key (KEK):** the key used to protect/wrap the DEK. With CMK, the KEK is a customer-controlled key in Key Vault or Managed HSM.
- The service uses **wrap/unwrap** operations to protect or recover DEK usability when needed.

```text
                    Microsoft Entra / Managed Identity
                                │
                      Appropriate key permissions
                                │
                                ▼
                 Azure Key Vault / Managed HSM
                       CMK = Key Encryption Key
                         wrap / unwrap
                                ▲
                                │
Application -- HTTPS --> Azure Storage Service
                                │
                       Data Encryption Key
                                │
                                ▼
                       Encrypted blob data
```

This is a **conceptual diagram**. The service may cache or optimize key operations; do not assume every single blob read triggers exactly one live call to Key Vault.

**Never export CMK keys into applications to embed in source code.** Normal applications only call the Storage API with appropriate data permissions. CMK configuration and Key Vault access belong to the infrastructure administration layer.

## 5. Two Configuration Levels: Account Encryption and Encryption Scope

The easiest point to confuse is **storage-account-level CMK** vs. **blob-level encryption scope**.

### Storage Account Level

A storage account has a default encryption configuration. You can let Microsoft manage the key or, for supported accounts/configurations, switch to a customer-managed key in an appropriate vault/HSM.

Advantage: a **uniform encryption policy for data using account-level encryption**. If one business unit owns the entire storage account, this can be a straightforward choice.

### Encryption Scope Level

An **Encryption scope** is an object created **inside a storage account** to declare an **encryption boundary for blobs assigned to that scope**. Each scope can use:

- **Microsoft-managed keys**, or
- A **Customer-managed key** linked to the scope under supported configurations.

Whichever scope a blob is written with determines its key policy. One storage account can hold multiple scopes, letting you separate data groups without provisioning a dedicated storage account for every group.

```text
Storage account: stappdata001
│
├── Account-level default encryption setting
│
├── Container: public-assets
│   └── Blob with no custom scope → uses account-level default
│
├── Container: invoices
│   └── Default encryption scope = scope-finance
│       ├── invoice-001.pdf → scope-finance
│       └── invoice-002.pdf → scope-finance
│
└── Container: hr-documents
    └── Default encryption scope = scope-hr
        └── employees.csv → scope-hr

scope-finance → Finance's customer-managed key
scope-hr      → HR's customer-managed key
```

**A scope is a key-selection boundary, not an access-authorization boundary.** If someone holds read permissions on blobs in both containers, using two encryption scopes does not automatically block them from reading those files via the Storage API. Pair scopes with Azure RBAC, ACLs (where supported), container settings, and network access controls.

### Quick Comparison

| Policy Level | Applicable Scope | When to Choose |
|---|---|---|
| Storage account, MMK | Data using account default encryption. | Simplicity, minimal key management. |
| Storage account, CMK | Data using account default encryption protected by a customer key. | Entire account shares one key management requirement. |
| Blob encryption scope, MMK | Blobs assigned to that scope. | Separate Microsoft-managed encryption boundaries. |
| Blob encryption scope, CMK | Blobs assigned to that scope with its specific key. | Each data group requires its own key lifecycle/policy. |

Scope selection occurs **at creation or write time via supported APIs**. Do not assume changing a container's default automatically converts all existing data to the new scope.

## 6. Default Encryption Scope and Preventing Overrides

At the **container level**, you can configure:

1. **Default encryption scope:** the scope applied by default when creating a blob in the container.
2. **Prevent encryption scope override:** forces blobs created in the container to adhere to the default scope instead of letting clients specify a different scope.

Example: container `invoices` sets default `scope-finance` and blocks overrides:

| Operation | Expected Result |
|---|---|
| Upload blob without passing an encryption scope | Uses the container's default `scope-finance`. |
| Upload blob explicitly passing `scope-finance` | Complies with container policy if other checks pass. |
| Upload blob explicitly passing `scope-hr` | Rejected due to override prevention setting. |
| Read blob with valid permissions | Azure Storage decrypts server-side using the blob's key. |

Why enforce a default: applications or ETL jobs can forget to pass the encryption scope parameter. Container policies reduce the chance of accidentally writing Finance data with another department's key.

### Lifecycle of Existing Blobs

Do not assume editing the default encryption scope, changing a container's scope, or updating policies today will **automatically re-encrypt all older blobs**. A blob already created under a specific encryption policy must go through an appropriate copy/rewrite/migration mechanism to move to a different scope.

Before migrating data, evaluate blob versions, snapshots, ADLS Gen2 paths, backup lifecycles, and concurrent reads/writes. Verify API behavior and restrictions for the blob type/account kind in your actual scenario.

## 7. Choosing Key Vault vs. Managed HSM

Azure provides key management services. Azure Storage CMK can integrate with **Azure Key Vault** and supported Managed HSM options.

| Criterion | Azure Key Vault | Azure Key Vault Managed HSM |
|---|---|---|
| Role | Stores and manages keys, secrets, and certificates within feature scope. | Managed HSM-based key management service emphasizing high key control. |
| Managed objects | Keys, secrets, and certificates in a vault. | Primarily cryptographic keys under an HSM model. |
| Authorization | Azure RBAC or supported access policy models; govern consistently. | Supported HSM governance/permission mechanisms. |
| Cost, operations | Fits a wide range of Azure workloads. | Different pricing, governance, and compliance profiles. |
| When to consider | Most standard CMK scenarios. | Strict HSM/key-control mandates and specialized organizational policies. |

Do not assume every key type, API version, or Storage encryption feature supports every Managed HSM configuration. Verify **storage account kind, scope support, key type, SKU, region, and tenant** against current requirements.

### Choosing Keys and Lifecycle Policies

For CMK:

- Create keys using algorithms/sizes supported by Azure Storage.
- Enable **soft delete** and **purge protection** on the key store as required by service support and organizational policy.
- Define who may **create, rotate, disable, delete, and recover keys**.
- Use recognizable key names, versions, and owner annotations.
- Prepare key backup/restore procedures compatible with the vault/HSM and data protection mandates.
- Verify network policies allow Storage to reach the key service via a supported method.
- Separate Storage administrators from key administrators to an appropriate degree.

**Disabling, deleting, or blocking access to a CMK can interrupt data reads/writes.** It is a powerful control and an operational risk. Never test "revoking a key to see what happens" on Production data.

## 8. Managed Identities and Key Access Permissions

For Azure Storage to use a CMK, the storage account or corresponding service configuration needs a valid **managed identity**. This identity receives least-privilege permissions so the service can access keys in Key Vault/HSM.

General workflow:

1. Configure a **system-assigned** or **user-assigned managed identity** per supported encryption type and features.
2. Select Key Vault/Managed HSM and create a compatible key.
3. Grant the identity permissions on the key to **read metadata and perform required wrap/unwrap operations**.
4. Select the key/Key URI in the storage account or encryption scope encryption settings.
5. Verify storage can use the key and create/read blobs within the intended scope.

### Distinguishing Control Plane and Data Plane

| Permission | What Is It Used For? | Example |
|---|---|---|
| **Storage account administration** | Create/edit encryption scopes, identities, diagnostic settings, account config. | Appropriate Azure RBAC on Storage account/resource group. |
| **Blob data access** | Read/write/delete blobs via the data plane within granted scope/rights. | `Storage Blob Data Reader` or `Storage Blob Data Contributor`. |
| **Key usage** | Allows the encryption service to use the key for wrap/unwrap. | Appropriate Key Vault permissions or role such as `Key Vault Crypto Service Encryption User` when RBAC applies. |
| **Key administration** | Create, rotate, disable, delete/recover keys. | Key management role/permissions separate from key usage permissions. |

Azure Resource Manager access such as `Contributor` on a storage account **does not automatically grant blob read permissions**. Likewise, blob read permissions do not grant key management in a vault. Verify the exact permission layer and whether the vault uses RBAC or access policies.

### Why Do Key Permission Errors Affect Applications?

When a storage account or encryption scope uses CMK, the service requires permissions and a network path to the key store. If the managed identity is deleted, wrap/unwrap permissions are revoked, or the key becomes unavailable, data operations relying on that key can fail even while the application still holds a valid Blob Data Contributor role.

Troubleshooting must separate two layers:

- **Data layer:** does the user/service principal have permission to access the blob?
- **Encryption layer:** can Azure Storage access and use the corresponding CMK?

Fixing the wrong layer can lead to granting overly broad permissions without resolving the failure.

## 9. Key Rotation, Versioning, and Recoverability

**Key rotation** means replacing a key or creating a new key version per policy to limit key-lifecycle exposure and meet organizational standards.

### Do Not Confuse Rotation with Re-Encrypting Every Blob

In envelope encryption, the CMK typically **protects data encryption keys**, rather than directly encrypting every byte of every blob. Consequently, rotating a CMK normally **does not require applications to re-download and re-upload all blobs**. The service handles key wrapping transitions according to its supported design.

However, this does **not** mean older data immediately stops depending on older key versions. Manage key versions and retention per Storage and vault requirements; never hastily delete key versions still needed to read existing data.

### Two Key Reference Models

- **Fixed version:** configuration points to one specific version; creating a new version does not necessarily make Storage switch automatically.
- **Versionless / auto-updating:** the service can detect newer versions where supported and apply them after an update window. Verify actual behavior for the key type, configuration, and API.

URI representation examples:

```text
Key with specific version:
https://kv-contoso.vault.azure.net/keys/blob-finance/<KEY_VERSION>

Versionless Key URI:
https://kv-contoso.vault.azure.net/keys/blob-finance
```

These illustrate key identifier syntax; support for versionless URIs and version transitions depends on the CMK configuration type. Never swap URLs in Production without checking support and rollback paths.

### Safe Rotation Workflow

1. Confirm current **identity, permissions, key status, and network access** are all healthy.
2. Confirm whether the active setup uses auto-rotation or manual rotation.
3. Create a new key version per policy while retaining the old version for the required period.
4. Let Storage pick up the update or apply the change via approved procedures.
5. Verify both older blobs and new blobs read/write successfully.
6. Monitor key access errors, Azure Monitor, and application logs.
7. Plan retirement of the old key version only after confirming no data or dependency still needs it.

### If a Key or Vault Suffers an Incident

Do not react by immediately creating a new key **with the same name** expecting old data to become readable. Identical names do not yield identical key material. If required key material or versions were deleted, follow the key service's valid **recover/restore** workflow within retention, backup, and organizational authorization boundaries.

Prepare ahead of time:

- Soft delete and purge protection are enabled.
- Key backup and recovery procedures are tested under the supported model.
- Owner/escalation contacts for both vault and storage account are documented.
- Alerts fire when keys approach expiration, get disabled, or when apps fail reads/writes.
- Runbooks exist for when another team alters identity, RBAC, networking, or the vault.

## 10. Double Infrastructure Encryption and Additional Options

Azure Storage offers **infrastructure encryption** (often called double encryption) in supported configurations. This adds a second infrastructure-level encryption layer alongside service-level SSE, using an independent mechanism/key per Azure design.

| Mechanism | Conceptual Scope | When to Consider |
|---|---|---|
| SSE with MMK | Default encryption at rest. | Most general workloads. |
| SSE with CMK | Encryption at rest with customer-controlled key wrapping. | Audit/regulatory key management requirements. |
| Encryption scopes | Select key policy per blob boundary. | One account holding multiple data groups needing separation. |
| Infrastructure encryption | Additional infrastructure encryption layer where supported. | Defense-in-depth mandates. |
| Client-side encryption | Application encrypts before sending to Storage. | Data must be encrypted with keys solely controlled client-side. |

**Infrastructure encryption does not replace CMK or encryption scopes**, nor is it automatically enabled merely because CMK was chosen. This option is typically decided **at storage account creation time** with limits on changing it later. Finalize requirements prior to deployment to avoid recreating accounts or migrating data.

### CMK vs. Customer-Provided Key (CPK)

A **customer-provided key** supplies an encryption key directly from the client alongside supported Blob requests via dedicated API mechanisms. It differs from a **CMK stored in Key Vault**, which Azure Storage references and uses to wrap data keys.

Never use the two terms interchangeably: they carry different key management responsibilities, lifecycles, API support, and failure modes.

## 11. Designing Encryption Scopes by Data Group

Suppose a company shares one storage account across three groups:

- **Public assets:** images, CSS, non-sensitive data.
- **Finance:** invoices and payment statements.
- **HR:** personnel records and sensitive documents.

An illustrative design:

| Data Group | Container | Encryption Policy | Data Permissions |
|---|---|---|---|
| Public assets | `public-assets` | Account default, MMK or per account policy. | Grant only needed permissions; "public assets" does not automatically mean anonymous access. |
| Finance | `invoices` | Default `scope-finance` using dedicated CMK; block overrides. | Finance teams/apps under least privilege. |
| HR | `hr-documents` | Default `scope-hr` using dedicated CMK; block overrides. | HR teams/apps with separate authorization. |

Objectives:

1. **Separate keys and key lifecycles** between Finance and HR.
2. **Separate data read/write permissions** via Entra ID/RBAC or appropriate ACLs.
3. **Control costs** when sharing an account instead of spinning up dozens of separate accounts.
4. **Simplify monitoring** through clear naming conventions for scopes, policies, and owners.

Do not infer that encryption scopes create **total isolation boundaries** between groups. The storage account remains a shared management boundary with account-level limits, quotas, networking, and settings. If legal mandates require isolation at the account, subscription, or tenant level, provision separate resources.

### Recommended Governance Registry

| Governance / Registry Attribute | Illustrative Value |
|---|---|
| Storage account | `stappdata001` |
| Container | `invoices` |
| Encryption scope | `scope-finance` |
| Key owner | Finance Security Team |
| Key store | Approved Key Vault |
| Data owner | Finance Applications |
| Rotation policy | Per internal policy |
| Recovery contact | Platform Security Team |
| Retention / immutability | Per data classification |
| Monitoring | Key audits, Storage error metrics, and alerts |

Never record raw key values or secrets in registries; record only resource identifiers and operational metadata.

## 12. Azure Portal Walkthrough: Configuring from Account to Container

The steps below serve as an **implementation template** to understand the workflow. Creating Key Vaults, storage accounts, encryption scopes, or storing blobs can incur charges. Execute only inside authorized subscriptions and resource groups.

### Step 1: Identify Storage Account and Service Type

1. Open the [Azure Portal](https://portal.azure.com/).
2. Select the right tenant, subscription, and resource group.
3. Open the target storage account and verify account kind and data types (Blob/Azure Files/ADLS Gen2...).
4. Check the account's **Encryption** settings to see whether it uses MMK or CMK.
5. Confirm **encryption scopes** are supported for the account kind and operations you need.

### Step 2: Prepare the CMK in Key Vault

1. Create or select an appropriate Key Vault/Managed HSM.
2. Confirm soft delete, purge protection, permissions, and network policies.
3. Create a key compatible with Azure Storage; record the Key URI/ID per organizational process.
4. Enable/prepare the managed identity used for CMK.
5. Grant required permissions so Storage can wrap/unwrap the key.

At this step, test access from Storage to the key store—do not merely verify that an administrator's browser can open Key Vault.

### Step 3: Create Encryption Scopes

1. In the storage account blade, open **Encryption scopes** under data management/security depending on portal layout.
2. Create `scope-finance` and select the matching key source:
   - Microsoft-managed key when only scope separation is needed without self-managed keys.
   - Customer-managed key when Finance requires independent key control.
3. If using CMK, pick the key vault/key or specify the URI as supported by the Portal.
4. Save and verify the scope shows active status, expected encryption source, and key details.
5. Create `scope-hr` similarly with its dedicated key if policy requires.

### Step 4: Bind Scope to a Container

1. Create container `invoices` or choose a container supporting this configuration.
2. Set default encryption scope = `scope-finance`.
3. Enable **Prevent encryption scope override** if every blob in the container must follow that scope.
4. Verify data permissions for applications accessing the container.
5. Test uploading a lab blob and observe the applied encryption scope.

Never run key deletion/disabling tests on containers holding live data. Tests that disrupt data readability belong in a separate test plan with safe copies.

## 13. Inspecting with Azure CLI

Azure CLI lets you observe configuration before creating or altering scopes. The commands below use placeholders and are primarily **read-only**.

### View Active Subscription

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Account:user.name}" \
  --output table
```

If operating on the wrong subscription, switch context before modifying Storage.

### View Account Encryption Settings

```bash
az storage account show \
  --name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{Name:name,Encryption:encryption,Identity:identity}" \
  --output json
```

The output helps inspect key source, encryption type, and managed identity when configured. Do not assume every JSON field is populated across every SKU/configuration.

### List Encryption Scopes

```bash
az storage account encryption-scope list \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

### View Scope Details

```bash
az storage account encryption-scope show \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --name "scope-finance" \
  --output json
```

Cross-check scope status, key source type, and key URI against project records. If CLI reports insufficient permissions or scope not found, verify subscription, resource group, account name, and control-plane permissions.

### Illustrative Command to Create an MMK Encryption Scope

The following command **modifies resources** and should only be run in an authorized lab environment:

```bash
az storage account encryption-scope create \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --name "scope-lab" \
  --source "Microsoft.Storage"
```

For a CMK-backed scope, key-source configuration typically uses `Microsoft.KeyVault` and a Key URI alongside the prepared managed identity/permissions. Exact CLI creation flags can vary by Azure CLI version, account kind, and key version requirements; check:

```bash
az storage account encryption-scope create --help
```

Avoid automating the CMK step before verifying exact flags and granted permissions in the deployment environment.

### Write a Blob Specifying a Scope

Example upload to a container when the scope exists and policy permits:

```bash
az storage blob upload \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "lab-documents" \
  --name "sample.txt" \
  --file "./sample.txt" \
  --encryption-scope "scope-lab" \
  --auth-mode login
```

This command **writes data**. The signed-in account must hold matching Blob data-plane permissions; the container and source file must exist. If the container enforces a default scope and blocks overrides, the specified scope must comply with policy.

### Confirm the Blob After Upload

```bash
az storage blob show \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "lab-documents" \
  --name "sample.txt" \
  --auth-mode login \
  --output json
```

Read supported metadata/properties to confirm the encryption scope. Field names can differ across CLI and API versions; inspect full JSON rather than relying solely on summary tables when needed.

## 14. Common Errors and Diagnostics

| Symptom | Likely Cause | How to Check |
|---|---|---|
| Cannot create encryption scope | Unsupported storage account kind, missing permissions, or incompatible feature. | Check SKU/kind, API support, control-plane permissions, and error message. |
| Creating CMK scope fails | Wrong Key URI, unconfigured identity, missing Key Vault permissions, or network block. | Check key status, managed identity, RBAC/access policies, firewall/private endpoints. |
| Container upload rejected when passing another scope | Container blocks overrides of its default scope. | Inspect default scope and prevent-override property. |
| App has Blob Data Contributor yet cannot read/write | Key access failure, disabled scope, or another data/backend error. | Separate Blob data-plane permission checks from CMK/scope health. |
| Older blobs still use previous encryption policy | Changing default scope does not auto-convert existing blobs. | Check blob's current scope and plan rewrite/migration. |
| Service loses read access after key is disabled | Storage cannot access required CMK. | Check key status, version, permissions, and recover per runbook. |
| Vault access fails after enabling firewall | Storage lost network path to vault. | Check routing, firewalls, private endpoints, and supported trusted-services bypass. |
| Rotation done yet old version still referenced | Service hasn't picked up new version or config pins a fixed version. | Check rotation policy, version URI, and update propagation time. |
| Unexpectedly high Key Vault/Managed HSM costs | Many scopes, key operations, vault/HSM tier, or log retention. | Analyze billing, metrics, and actual usage. |
| CMK enabled yet audit fails | Missing rotation/recovery policies, logs, or proper authorization separation. | Compare key governance evidence against audit requirements. |

### Runbook: An Application Suddenly Cannot Access Blobs

1. Identify the storage account, container, blob, UTC timestamp, and associated request ID.
2. Inspect storage account status, returned error codes, and Azure Monitor/Storage logs.
3. Confirm the caller holds appropriate data permissions, the token hasn't expired, and network access isn't blocked.
4. Check the blob/container encryption scope; determine whether it uses MMK or CMK.
5. If using CMK, check managed identity, wrap/unwrap permissions, key/version status, and connectivity to the vault.
6. Check recent change logs: role assignments, Key Vault firewall, key rotation, disabled/deleted keys or scopes.
7. If key recovery is required, follow the organizationally approved runbook, prioritizing recovering/restoring the original key and needed version.
8. After remediation, test reading an **old blob** and writing/reading a **new blob**; monitor errors and record evidence.

Never disable encryption or grant broad Owner access to everyone as a temporary workaround for an undiagnosed failure. Key management permissions carry major blast radius, especially for data shared across multiple applications.

## 15. Monitoring, Auditing, and Cost Control

When operating Azure Storage with CMK, observe both **Storage** and **Key Vault/HSM**:

- **Storage metrics and logs:** request errors, latency, read/write availability, and configuration change events.
- **Azure Activity Log:** storage account/encryption scope management actions and control-plane changes.
- **Key Vault/HSM diagnostic logs:** key operations, denied access, permission/policy updates as provided by log sources.
- **Key lifecycle monitoring:** enabled/disabled state, expiration dates, rotation policies, and recovery alerts.
- **Identity/RBAC changes:** modifications to managed identities, security groups, or vault permissions.
- **Alert rules:** sudden Storage error spikes, loss of key access, or sustained application failures.

### Defense Through Separation of Duties

A governance model may separate:

1. **Storage operator:** manages containers, scopes, and storage settings.
2. **Security/key custodian:** manages key policies, rotation, recovery, and approves vault permission changes.
3. **Application identity:** holds only necessary Blob data-plane permissions.
4. **Storage managed identity:** holds only required cryptographic permissions on configured keys.
5. **Auditor:** holds read-only access to logs, settings, and reports within permitted scope.

Administrative access is granted per actual role; the roles above form a **responsibility model**, not mandatory built-in Azure role names.

### Costs to Watch

| Item | Where Does Cost Originate? |
|---|---|
| Storage | Capacity, tiers, read/write transactions, replication, and data features. |
| Key Vault | Vault tier, cryptographic operations, key/certificate counts, logging per plan. |
| Managed HSM | Service configuration, usage, and key management operations. |
| Encryption scopes | Possible feature/scope-related charges per current pricing model and SKU. |
| Diagnostic logs | Ingestion, retention, and storage/Log Analytics destination. |
| Networking / private endpoints | Networking components and data transfer, if deployed. |

Use the **Azure Pricing Calculator** and current regional/SKU rate cards to decide. Every CMK encryption scope introduces additional permissions, keys, and runbooks to manage—avoid creating hundreds of scopes when data groups only need one shared policy.

## 16. Practice Exercise: Building Encryption Policies for Finance and HR

**Context:** An application stores product images, invoices, and HR records in Blob Storage. Finance and HR require managing their own separate keys and proving data uses the right key. Product images have no separate CMK requirement. The organization wants to control costs while maintaining permission separation.

Assumed parameters:

| Component | Value |
|---|---|
| Storage account | `stappdata001` |
| Images container | `public-assets` |
| Invoices container | `invoices` |
| HR container | `hr-documents` |
| Finance encryption scope | `scope-finance`, Finance CMK |
| HR encryption scope | `scope-hr`, HR CMK |
| App permissions | Each app reads/writes only its respective container |
| Container policy | Override disallowed on Finance and HR |

### Tasks

1. Distinguish the MMK default encryption portion from the two CMK scopes.
2. Sketch the Key Vault/managed identity and Storage relationship for both data groups.
3. Propose default encryption scope and prevent-override settings for each container.
4. List permissions required for the **storage managed identity** and the application identities.
5. Outline verification steps when creating new blobs and reading older blobs.
6. Design a rotation and recovery procedure when a key version encounters an issue.
7. List log sources to monitor and evidence to retain for audits.
8. Evaluate when Finance and HR should be split into separate storage accounts.

### Reference Solution

**Separation:**

```text
Storage account: stappdata001
|
|-- public-assets  ----------> account default encryption (MMK)
|
|-- invoices       ----------> scope-finance (Finance CMK)
|      |                          |
|      +-- no override           +--> Key Vault / key-finance
|
+-- hr-documents   ----------> scope-hr (HR CMK)
       |                          |
       +-- no override           +--> Key Vault / key-hr

Storage managed identity: key-usage permissions scoped as needed
Finance app identity:     Finance data permissions, no key administration
HR app identity:          HR data permissions, no key administration
```

**Testing:** upload a test blob into `invoices` without passing a scope and verify it receives `scope-finance`; attempting `scope-hr` must be rejected when override is blocked. Finance accounts cannot read HR if data permissions are properly configured. Never disable live keys merely to prove a policy works.

**Rotation:** generate a new version per runbook, monitor service adoption of the version, verify reads/writes on both older and newer blobs, and retain the older key version until certainty exists that it is no longer needed. Maintain backups/recovery and clear ownership.

**When to split accounts:** if HR requires completely separate firewalls, private endpoints, retention mandates, quotas, subscriptions/tenants, or administrative boundaries, encryption scopes inside one account may fall short. In that case, two separate storage accounts are the sounder choice.

### Acceptance Criteria

- Clearly separated **encryption** from **data read permissions**.
- Each sensitive container has the required encryption scope and key.
- Managed identity holds only necessary key-usage permissions, without arbitrary broad privileges.
- Rotation and recovery processes ensure both current and historical data remain readable.
- Error testing, audit trails, and cost monitoring are in place prior to Production.

## 17. Self-Check Knowledge Quiz

**Question 1.** With default Azure Storage Service Encryption, must an application encrypt data itself before uploading to achieve encryption at rest?

A. Yes, otherwise Azure stores plaintext.  
B. No; Storage automatically encrypts at rest.  
C. Only if uploaded over HTTPS.

**Answer: B.** SSE encrypts data at the service layer. HTTPS protects data in transit, while client-side encryption is a separate option when apps have stricter requirements.

**Question 2.** What is the primary difference between MMK and CMK?

**Answer:** Who manages the lifecycle of the key protecting data encryption keys. CMK lets customers control keys in Key Vault/HSM under supported setups, while Storage still performs SSE encryption/decryption.

**Question 3.** Does an encryption scope automatically block Finance users from reading HR blobs?

**Answer:** No. Scopes separate key policies, not data access permissions. You must configure Entra ID, RBAC/ACLs, and network policies.

**Question 4.** Container `invoices` has default `scope-finance` and prevent override enabled. What happens when a client uploads with `scope-hr`?

**Answer:** The request must be rejected because the specified scope violates container policy.

**Question 5.** Does changing a container's default encryption scope automatically migrate all existing blobs to the new scope?

**Answer:** No. You must evaluate an appropriate rewrite/copy/migration mechanism to change the scope of existing data.

**Question 6.** An app holds Storage Blob Data Contributor yet fails to read CMK-encrypted data. What else must be checked?

**Answer:** Key status, version, managed identity, key-usage permissions, and connectivity from Storage to Key Vault/HSM. Blob data-plane permissions alone are insufficient if Storage cannot use the CMK.

**Question 7.** Should you immediately delete an older key version right after creating a new CMK version?

**Answer:** No. Verify dependencies and readability of older data first; deleting/disabling a still-needed version can cause loss of data accessibility.

**Question 8.** Is infrastructure encryption synonymous with encryption scope?

**Answer:** No. Infrastructure encryption adds an extra infrastructure encryption layer; encryption scope selects the key boundary/policy for blobs.

**Question 9.** Are customer-managed keys and customer-provided keys the exact same mechanism?

**Answer:** No. CMK is a key referenced by Storage whose lifecycle is managed via vault/HSM; CPK is supplied directly by the client in supported APIs.

**Question 10.** Why monitor both Storage logs and Key Vault logs?

**Answer:** Storage logs help pinpoint failing data requests, while Key Vault logs and key lifecycle signals distinguish permission, network, rotation, or key-state faults so you fix the true root cause.

Effective Azure Storage encryption design is about choosing the right **policy boundaries, permissions, and key lifecycles**. MMK simplifies operations; CMK strengthens key control; encryption scopes group data at the blob/container level. All three must pair with authorization, monitoring, rotation, and recovery so data stays both protected and reliably accessible when applications need it.

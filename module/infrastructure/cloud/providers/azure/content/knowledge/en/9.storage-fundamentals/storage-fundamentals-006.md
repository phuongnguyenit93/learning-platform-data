# Shared Key, Shared Access Signature, and User Delegation SAS

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; we also learn how to deploy, monitor, secure, and control costs for an Azure application architecture. In the **Azure Storage Fundamentals** chapter, a critical security decision is: how, for how long, and with what permissions are applications and external users allowed to access blobs, files, or other storage services?

Azure Storage provides multiple authentication and authorization mechanisms. In this lesson, we focus on **Shared Key** (storage account keys), **Shared Access Signature (SAS)**, and the **user delegation SAS** variant for Blob Storage. They are related yet not synonymous. Choosing the wrong one can inadvertently grant someone receiving an invoice download link overly broad access across an entire storage account.

After this lesson, you will be able to:

- Distinguish authentication via an account key from temporary delegated access via a SAS.
- Compare **service SAS**, **account SAS**, and **user delegation SAS** by signing source, scope, permission capability, and revocation.
- Read key parameters in a SAS token such as `sp`, `se`, `sr`, `spr`, and `sig`.
- Issue a **user delegation SAS** for a single blob using the Azure CLI and Microsoft Entra ID following least privilege.
- Design the issuance, distribution, restriction, and revocation lifecycle of SAS tokens; troubleshoot common errors.
- Evaluate when to disable Shared Key authorization for Blob Storage and its operational consequences.

## 1. The Problem: Sharing Data Without Exposing Account Keys

Suppose an order management application stores invoice files in Azure Blob Storage:

```text
Storage account: stordersprod
  |
  +-- Blob container: invoices (private)
         |
         +-- 2026/INV-1042.pdf
         +-- 2026/INV-1043.pdf
```

A customer needs to download only invoice `INV-1042.pdf` for 10 minutes. You can grant access in several ways:

1. **Avoid:** embedding the storage account key in the browser or mobile app; this key carries very broad privileges.
2. **Viable:** the server generates a **SAS URL** for that exact blob, with read-only permission and a short lifetime; the browser uses this URL directly against Blob Storage.
3. **Preferred for Azure-hosted backends:** use **managed identity + Azure RBAC** so the backend itself accesses Storage via Microsoft Entra ID without storing an account key.

Invoice download sharing flow:

```text
Customer --> Orders API (authenticated, verifies invoice ownership)
                          |
                          | Backend uses Entra ID / managed identity
                          | to request a user delegation key and create a SAS
                          v
               SAS to read 1 blob, expires in 10 minutes
                          |
                          v
             Customer downloads blob directly over HTTPS
                          |
                          v
                    Azure Blob Storage
```

A SAS is a **bearer credential**: anyone holding the URL/token can use it within the signed permissions and conditions, even if they were not the original intended recipient. Therefore, before issuing a SAS, the API must **authenticate the requester and enforce business-layer authorization checks**. A SAS does not inherently know which customer owns a given invoice.

## 2. What Is Shared Key Authorization?

Each storage account of a type supporting Shared Key has **account access keys** (typically two keys, `key1` and `key2`). These are **storage-account-level** secrets issued by Azure and used to sign Shared Key requests or account-key-based SAS tokens.

When a client uses Shared Key authorization, the client computes a cryptographic signature from the request contents and the account key. The Storage service verifies the signature to authenticate the request.

```text
Application holding account key
        |
        | Computes Shared Key signature for request
        v
HTTP request + Authorization header
        |
        v
Azure Storage verifies signature using storage account key
        |
        v
Accepts or denies per applicable authorization policy
```

**Key characteristic:** an account key is a very broadly privileged credential at the storage account scope. It does not naturally map to granular permissions for individual Microsoft Entra ID users. Anyone holding the account key can perform extensive data operations or issue SAS tokens across supported services, and attributing actions to specific individuals sharing the same key becomes difficult.

### 2.1. Why Not Distribute Account Keys?

If you place an account key on a client machine or frontend application:

- Recipients can extract and reuse the key.
- An account key cannot be scoped down to a single blob and a short time window like a SAS.
- Revoking the key disrupts every other app or SAS still relying on that key.
- Accountability to a specific actor is lost when multiple workloads share the same key.
- The key can leak via repositories, environment variables, configuration backups, error messages, or monitoring tools.

When Shared Key must be used for legacy compatibility, treat it as a high-privilege secret: store it in an appropriate secrets manager, restrict who can read the key, document access procedures, and plan a migration to Microsoft Entra ID where supported by the service.

### 2.2. Two Account Keys Support Rotation

Storage accounts typically provide two keys to enable phased **key rotation**:

1. Inventory every client, service, configuration store, and SAS depending on the key being rotated.
2. Migrate clients to the alternate key via a safe rollout process and confirm access works.
3. **Regenerate** the old key and update systems that need the new key.
4. Test, monitor authentication errors, and put rotation on a recurring schedule.

**Regenerating an account key invalidates signatures/SAS tokens signed with that exact key** and can disrupt unmigrated clients. Never regenerate both keys back-to-back without a full dependency inventory. If a key leaks, handle it through security incident response rather than relying on SAS expiration dates.

## 3. What Is a SAS?

A **Shared Access Signature** is a token containing access conditions signed by a valid key. A client sends the SAS along with a request to Azure Storage—typically in the **URL query string**—so the service can verify permissions without giving the client the account key or requiring the client to sign in with Entra ID.

Illustrative example with the **actual signature redacted**, unusable for access:

```text
https://stordersprod.blob.core.windows.net/invoices/2026/INV-1042.pdf
    ?sv=<service-version>
    &sp=r
    &se=2026-11-20T10%3A10%3A00Z
    &spr=https
    &sr=b
    &sig=<redacted-signature>
```

In practice, the URL sits on a single line. The timestamp above is simply an illustrative past example showing structure, not a currently valid SAS.

A SAS is not an account key, yet **it remains sensitive information**. Anyone possessing a valid SAS can execute the allowed actions within the token's active scope and lifetime. Never treat a URL containing `sig` as a harmless public link.

### 3.1. Common SAS Parameters

| Parameter | Name | Meaning |
|---|---|---|
| `sv` | Signed version | Storage protocol version used to sign/process the SAS |
| `sp` | Signed permissions | Permissions such as read, write, create, delete, list, depending on SAS type and service |
| `st` | Signed start | Validity start time, if specified |
| `se` | Signed expiry | Expiration time |
| `spr` | Signed protocol | E.g., `https` to allow HTTPS only |
| `sip` | Signed IP | Public IP range allowed to use the SAS, if specified and compatible with the network path |
| `sr` | Signed resource | Resource type in service/user delegation SAS, e.g., blob (`b`) or container (`c`) |
| `ss` | Signed services | Services covered in an account SAS |
| `srt` | Signed resource types | Resource types covered in an account SAS |
| `si` | Signed identifier | Stored access policy reference for an eligible service SAS |
| `sig` | Signature | Cryptographic signature protecting the integrity of the signed parameters |

Not every SAS carries the exact same set of parameters. For example, a **user delegation SAS** includes additional delegation key/identity fields such as `skoid`, `sktid`, `skt`, `ske`, `sks`, and `skv`. Those fields do not turn the SAS into an end-user login token.

Common permission abbreviations in Blob Storage:

| Symbol | Permission | Notes |
|---|---|---|
| `r` | Read | Read content/properties per supported permissions |
| `a` | Add | Append data for supported blob types |
| `c` | Create | Create resources within SAS scope |
| `w` | Write | Write/update data per resource type |
| `d` | Delete | Delete data; powerful permission that should be restricted |
| `l` | List | List containers/blobs within supported scope |

Exact permissions depend on **SAS type, service, and REST API version**. Do not assume an `sp` string behaves identically across Blob, Queue, File, and Table. In code, use official SDKs/CLIs to generate valid permission sets rather than hand-crafting signatures.

### 3.2. Scope and Permissions Determine Risk

A SAS created for **one blob with only `r` permission for 10 minutes** has a far smaller blast radius than a SAS for a whole container with `rlwd` for multiple days. Design principles:

- Pick the narrowest resource: blob instead of container when only one file is needed.
- Grant only required permissions: `r` instead of `w`, `d`, or broader rights.
- Set a short lifetime, accounting for network latency and clock drift.
- Enforce `spr=https`, and consider `sip` if client source IPs are stable and within service processing scope.
- Avoid leaking SAS tokens into logs, mass emails, URL analytics, client-side error reports, or support tickets.

If `st` is omitted, the SAS can take effect immediately as processed by the service. When `st` is needed, watch for **clock skew** between clients and Azure Storage: setting the start time to exact "now" can trigger transient failures in some environments. When no delayed start is required, omitting `st` is often safer.

## 4. Three Types of SAS to Distinguish

Azure Storage supports distinct SAS types differing in **signing key source** and **scope**:

1. **Service SAS:** signed with the **storage account key**, granting access to resources in **one specific Storage service**; for Blob Storage, typically a blob or container.
2. **Account SAS:** also signed with the **storage account key**, capable of granting operations across **multiple services/resource types** declared in the token.
3. **User delegation SAS:** signed with a **user delegation key** issued by the Blob service based on a **Microsoft Entra ID** identity. This type is for **Blob Storage** (including supported Data Lake Storage Gen2 scenarios), not a universal SAS mechanism for Queue, Table, or Azure Files.

### 4.1. Core Comparison Table

| Criterion | Service SAS | Account SAS | User Delegation SAS |
|---|---|---|---|
| Signing material | Account key | Account key | User delegation key obtained via Entra ID |
| Typical scope | Blob, container, or single-service resource | Multiple services and resource types declared in token | Blob/container within supported scope |
| Requires holding account key when issuing? | Yes | Yes | No |
| Requires Microsoft Entra ID when issuing? | Not mandatory | Not mandatory | **Yes** |
| Stored access policy support | **Yes** for eligible service SAS | No | No |
| Primary revocation methods | Expiration, modify/delete stored access policy, or rotate account key | Expiration or rotate account key | Expiration or revoke user delegation keys on the account |
| Service scope | Single service | Can span multiple services | Blob Storage |
| Recommendation for Blob Storage | Use when compatibility or specific policy requires it | Only when account SAS scope is genuinely needed | **Preferred** whenever possible |

**Do not confuse a service SAS with a user delegation SAS** merely because both can grant read access to a blob. The crucial difference is who can generate the signature and what credentials do the signing.

### 4.2. Service SAS

A Service SAS is useful when delegating access to resources within one service, such as downloading a blob or writing to a designated container. Because the token is signed with the storage account key, the issuer still needs strong key access at the storage account level.

Example scenarios:

- A legacy system needs to issue a blob download URL to a partner.
- A SAS issuance workflow uses a container's **stored access policy** to govern lifetimes/permissions or support policy-based revocation.

A **stored access policy** is a policy defined on a container with an identifier and supported conditions. When a service SAS references that identifier via `si`, modifying or deleting the policy affects SAS tokens tied to it (propagation may take a brief interval). Not every SAS uses a stored access policy; an **ad hoc SAS** embeds its conditions directly in the token.

A SAS can inherit permissions/expiry from a stored access policy per service rules, so avoid conflicting or duplicate declarations between token and policy. Use official SDKs/CLIs and verify the effective policy settings.

### 4.3. Account SAS

An Account SAS specifies scope using `ss` (**services**) and `srt` (**resource types**) alongside `sp` permissions and expiry. It is useful for operations not covered by a service SAS, such as certain account-level or service-level operations supported by the Storage API.

Because an Account SAS can span a broad scope, the risk of over-provisioning is greater than with a single-blob service SAS. It also does **not** support stored access policies. If an Account SAS leaks, revocation options are limited: wait for expiration or rotate the signing account key, where the latter can cause wide disruption.

### 4.4. User Delegation SAS

A User delegation SAS is the preferred option when a client needs temporary URL access to Blob Storage and the backend can authenticate using Microsoft Entra ID.

General workflow:

1. The workload authenticates with Microsoft Entra ID, preferring a **managed identity** when hosted on Azure.
2. The workload holds appropriate permission to request a **user delegation key** from the Blob service.
3. The Blob service issues a time-limited delegation key to the authenticated principal.
4. The workload signs the SAS using that delegation key with the chosen scope, permissions, and lifetime.
5. The client receives the SAS URL and accesses Blob Storage directly; the client **never** holds the account key or the backend's Entra ID token.

```text
Backend (managed identity)
          |
          | Microsoft Entra ID token
          v
Blob service: requests user delegation key
          |
          | Time-limited user delegation key
          v
Backend signs user delegation SAS
          |
          | SAS URL to read 1 blob
          v
Browser / partner ---> Blob Storage validates SAS ---> Blob access permitted
```

A delegation key has a maximum lifetime of **7 days** per service limits. Any SAS signed with it cannot remain valid longer than the key itself; in practice, keep the SAS much shorter—such as a few minutes for a single download. A user delegation SAS **cannot be bound to a stored access policy**.

A major advantage is that the backend never reads the storage account key. Effective permissions when redeeming a user delegation SAS are constrained by the data permissions of the Entra ID principal that requested the key as well as the permissions/constraints in the SAS; a read-only principal cannot arbitrarily mint a SAS that deletes data. Interactions across Azure RBAC, ACLs when hierarchical namespace is enabled, and REST API rules depend on the service and should be tested against real data objects.

## 5. What Permissions Are Required to Create a User Delegation SAS?

To request a user delegation key, the principal needs the following management action:

```text
Microsoft.Storage/storageAccounts/blobServices/generateUserDelegationKey/action
```

This action must be assigned at the **storage account scope or an appropriate parent scope** (resource group/subscription); assigning it solely on a single container is insufficient for an account-level user delegation key request.

The built-in **Storage Blob Delegator** role provides the permission to request delegation keys. For data operations such as reading blobs, the issuer also needs the corresponding data-plane role, such as **Storage Blob Data Reader** on the target container. Another built-in role containing the required actions may work, but always inspect actual actions and scope rather than guessing from role names.

Example requirements:

| Task | Permission to Evaluate | Scope |
|---|---|---|
| Request user delegation key | `generateUserDelegationKey/action` | Storage account or parent scope |
| Read blob | Blob data-plane read permission | Supported container/blob scope |
| Write or delete blob | Appropriate data-plane write/delete permission | Only where genuinely required by business logic |
| Workload authentication | Entra ID token, e.g., managed identity | Identity running the backend |

**Reader** at the Azure Resource Manager layer does not automatically grant permission to read blob contents. Management-plane **Contributor** should likewise not be treated as a clear substitute for data permissions. Pick the exact data-plane role and avoid subscription-wide grants just to issue a SAS for one file.

An identity may be permitted to request delegation keys at the account level while holding data read access on only one container; combining scopes this way avoids granting unnecessary data permissions across the entire storage account.

## 6. Secure SAS Issuance Workflow

Before generating a SAS, the backend must answer:

1. **Who is requesting?** An authenticated user or an authorized system?
2. **Which resource?** A single blob, a container, or an account-level operation?
3. **Which action?** Read-only (`r`), or is there a valid business reason for write (`w`), create (`c`), or delete (`d`)?
4. **For how long?** From a few minutes for a download to a task-appropriate window—never multi-day by default.
5. **Network conditions?** Enforce HTTPS; should `sip` also be restricted?
6. **Who is signing?** Which managed identity/Entra principal, with which RBAC roles and scopes?
7. **If leaked?** Is there a viable revocation path and anomaly monitoring?

For the invoice scenario, recommended parameters:

| Condition | Recommended Value |
|---|---|
| Resource | Exact blob `invoices/2026/INV-1042.pdf` |
| Permission | `Read` |
| TTL | 10 minutes |
| Protocol | HTTPS |
| Issuer | Backend with managed identity, allowed to read container |
| Recipient | Client authenticated by backend and verified as invoice owner |
| Leak response | Short expiry; if emergency revocation is needed, assess impact of revoking delegation keys |

Never issue a container-level SAS with List and Delete permissions simply because the frontend needs to download one PDF file.

## 7. Hands-On: Generating a User Delegation SAS with Azure CLI

This exercise uses **Azure CLI on Bash** (such as Azure Cloud Shell), a **Blob Storage account**, and an existing private blob. Commands below are configuration templates; do not assume resources or identities already exist in your tenant.

**Prerequisites:**

- Storage account `stordersdev001` in resource group `rg-orders-dev` with container `invoices`.
- The container holds a blob named `2026/INV-1042.pdf` (folders shown in Blob Storage are merely part of the blob name unless hierarchical namespace is enabled).
- The operator is signed into Azure CLI with Microsoft Entra ID and holds required blob read permissions.
- The user or an administrator authorized to create role assignments has granted `generateUserDelegationKey/action` at the right scope.
- The storage account permits network requests from the lab environment; if using a firewall or private endpoint, satisfy those network prerequisites.

### 7.1. Verify Subscription and Resources

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-orders-dev"
ACCOUNT="stordersdev001"
CONTAINER="invoices"
BLOB="2026/INV-1042.pdf"

az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,id:id,allowSharedKeyAccess:allowSharedKeyAccess}" \
  --output json
```

The `allowSharedKeyAccess` field reflects whether Shared Key authentication is allowed. If the property is not explicitly set, do not assume Shared Key is blocked on the account; verify effective behavior against documentation for the account kind and organizational policy.

### 7.2. Prepare Permissions for the Issuer

For an **Entra ID user** signed into Azure CLI, an administrator with role-assignment permissions can demonstrate with:

```bash
STORAGE_SCOPE=$(az storage account show \
  --resource-group "$RG" --name "$ACCOUNT" \
  --query id --output tsv)

CONTAINER_SCOPE="$STORAGE_SCOPE/blobServices/default/containers/$CONTAINER"
USER_OBJECT_ID=$(az ad signed-in-user show --query id --output tsv)

# Appropriate RBAC admin permissions are required to run the two commands below.
az role assignment create \
  --assignee-object-id "$USER_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Delegator" \
  --scope "$STORAGE_SCOPE"

az role assignment create \
  --assignee-object-id "$USER_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Reader" \
  --scope "$CONTAINER_SCOPE"
```

If the issuer is a **managed identity/service principal**, replace `USER_OBJECT_ID` with that identity's **principal Object ID** and pass `--assignee-principal-type ServicePrincipal` where appropriate. For production systems, grant roles via IaC or an approved governance workflow rather than having the backend create role assignments itself.

Role assignments can take time to propagate. Letting a user request delegation keys via Azure RBAC does not equate to letting that user read account keys; keep those two permissions separate.

### 7.3. Generate a 10-Minute Read SAS for One Blob

Use Azure CLI with Microsoft Entra ID tokens:

```bash
# Cloud Shell Bash / GNU date: expiry time in UTC.
EXPIRY=$(date -u -d '+10 minutes' '+%Y-%m-%dT%H:%MZ')

# Store token in a shell variable to avoid printing the token to the terminal.
SAS=$(az storage blob generate-sas \
  --account-name "$ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$BLOB" \
  --permissions r \
  --expiry "$EXPIRY" \
  --https-only \
  --auth-mode login \
  --as-user \
  --output tsv)
```

Depending on Azure CLI version, option syntax may vary; check command help in your active environment. The critical flags are `--auth-mode login --as-user`: **issuing a user delegation SAS via Entra ID**, rather than silently fetching an account key for Shared Key signing.

If constructing a URL for the backend to return over HTTPS to an authorized user:

```bash
# Example uses a simple blob name with no characters requiring URL encoding.
SAS_URL="https://$ACCOUNT.blob.core.windows.net/$CONTAINER/$BLOB?$SAS"

# Never print SAS_URL or SAS to logs, terminal, or pipeline output.
# Backend must transmit the URL over a secure channel after verifying the recipient.
```

For blob names containing spaces, `#`, `?`, or special characters, URL-encode **the blob path segment** properly (do not double-encode the SAS query string). In real applications, use the Azure Storage SDK to construct URLs instead of manual string concatenation.

A SAS expires at its signed expiry time. You cannot "extend" an existing SAS by editing the `se` parameter in the URL because the signature protects the token contents. When a new lifetime is needed, the backend must mint a new SAS.

### 7.4. Why Issue a SAS Only After Business Authorization Checks?

A blob container may store data belonging to many customers. If an API takes `invoiceId` from a client and immediately generates a SAS without checking the customer–invoice relationship, a user can try other IDs to fetch documents that are not theirs. Proper flow:

1. Backend authenticates the user via the application identity system.
2. Backend looks up the invoice and verifies the user is authorized to access that record and document.
3. Backend resolves the blob path from trusted server-side data, never using an arbitrary client-supplied path directly.
4. Backend mints a short-lived user delegation SAS to read **that single blob**.
5. Backend returns the URL over HTTPS without recording the full URL in logs.

In architectures requiring per-download revocation or anti-URL-sharing guarantees, a better approach is **proxying downloads through the backend**: the client authenticates to the backend, and the backend reads the blob using its managed identity and streams it back without handing a bearer SAS to the client. The tradeoff is higher compute and bandwidth load on the backend.

## 8. Shared Key Signing Example: When to Use and What to Avoid

Legacy systems sometimes issue a **service SAS** from an account key. Azure CLI supports key authentication when allowed by the account and operator permissions:

```bash
# Illustrative only in a sandbox / test storage account.
# Avoid letting Azure CLI or pipelines fetch account keys in production.
EXPIRY=$(date -u -d '+15 minutes' '+%Y-%m-%dT%H:%MZ')

SERVICE_SAS=$(az storage blob generate-sas \
  --account-name "$ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$BLOB" \
  --permissions r \
  --expiry "$EXPIRY" \
  --https-only \
  --auth-mode key \
  --output tsv)
```

Not every CLI user is allowed to read account keys. If an SDK or CLI automatically calls **List Keys**, that is a privileged operation that must be controlled. **Never broaden account key read permissions as a quick fix for SAS generation errors** when a user delegation SAS satisfies the requirement.

For an **account SAS**, the CLI offers account-wide operations such as `az storage account generate-sas`. This signs with the account key and accepts signed services (`ss`), resource types (`srt`), and permissions (`sp`). Because its scope can be wider than a service SAS, inventory allowed actions and assess impact before use. Never use an account SAS as the default for sharing a single blob.

### 8.1. Shared Key Authorization and Blocking Shared Key

For services supporting **disallow Shared Key authorization**, organizations can set `allowSharedKeyAccess=false` to reject requests authenticated with Shared Key. For **Blob Storage**, this also rejects **account-key-signed service SAS / account SAS** tokens under the Shared Key mechanism; **user delegation SAS** and Microsoft Entra ID-authenticated requests can continue working when permissions and conditions align.

Do not conclude this setting behaves identically across **every service inside a storage account**; effects on Azure Files and compatible protocols or features must be verified against specific service documentation. Switching to `allowSharedKeyAccess=false` can break legacy apps, file share mounts, or existing pipelines if not inventoried beforehand.

Before blocking Shared Key:

1. Inventory all applications, connection strings, and `List Keys` usages.
2. Locate existing account-key-signed service/account SAS tokens and where they are distributed.
3. Audit SDKs/CLIs, backup systems, ETL jobs, integration tools, and other services depending on the account.
4. Migrate eligible workloads to Microsoft Entra ID/managed identities and user delegation SAS.
5. Test in non-production, prepare a rollback plan, and monitor `403` errors after the change.

Never treat disabling Shared Key as complete protection against data leaks: you still must govern RBAC, active SAS tokens, firewalls/network rules, private endpoints, logging, and data lifecycle.

## 9. Revoking Access: Critical Differences

Once a SAS is issued, Azure Storage validates the signature without calling back to the application backend on every download. This gives strong performance while making **revoking a single specific token** harder than in a system checking session state on every request.

| Access Type | Typical Revocation | Impact to Watch |
|---|---|---|
| Direct Shared Key | Regenerate the active account key | Disrupts all clients still holding the old key |
| Ad hoc Service SAS | Expire or regenerate the signing account key | Can affect many SAS tokens/clients |
| Service SAS referencing stored access policy | Modify/delete the stored access policy; or rotate account key | Modifying the policy affects **all SAS tokens referencing** that policy |
| Account SAS | Expire or regenerate the signing account key | Has no stored access policy for group revocation |
| User delegation SAS | Expire or **revoke user delegation keys** on the storage account | Can invalidate **all SAS tokens** signed by the revoked delegation keys |

For sensitive data, design **very short TTLs**, since instant revocation of *one individual URL* is usually unavailable. User delegation SAS does not support stored access policies.

### 9.1. Revoking User Delegation Keys Does Not Revoke a Single Token

Suppose a backend issues 100 user delegation SAS tokens over a period using a delegation key. If one SAS leaks, revoking user delegation keys at the storage account level can invalidate other SAS tokens signed by the revoked keys. Therefore, assess blast radius and notify affected systems before executing an emergency revocation.

Revoking or removing the issuer principal's RBAC roles stops new keys from being requested, yet **do not assume all already-signed SAS tokens immediately stop working**. Already-issued keys and tokens have independent lifetimes and states; invoke the delegation-key revocation operation when active SAS tokens must be invalidated per service mechanics.

### 9.2. Stored Access Policies Do Not Apply to User Delegation SAS

A stored access policy lets an account-key-signed **service SAS** reference a container-level policy. Changing permissions or expiry on the policy affects linked SAS tokens per Storage mechanics. This is helpful for legacy systems needing group-level revocation, though it still depends on account keys.

If you simultaneously require:

- Zero reliance on account keys, and
- Immediate revocation of *individual links*,

then a short-TTL user delegation SAS plus strict issuance controls may still fall short. Consider **proxying via the backend**, an application-controlled token/authorization architecture, or deliberate object renaming/relocation where appropriate, rather than expecting SAS to provide per-URL revocation.

## 10. Common Configuration Errors and Root Causes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `403 AuthorizationPermissionMismatch` | SAS lacks needed permission or user delegation SAS issuer lacks data rights | Compare `sp`, RBAC/ACLs, and actual Blob API operation |
| `403 AuthenticationFailed` | Invalid signature, altered token, wrong version, or expired SAS | Check URL construction, `sig`, `sv`, `st`, `se`, UTC clock |
| Cannot obtain user delegation key | Principal lacks `generateUserDelegationKey/action` or role scope is too narrow | Check `Storage Blob Delegator` at storage account/parent scope |
| `--as-user` fails | Not signed into Entra ID in right tenant/subscription, role pending, or outdated SDK/CLI | Verify `az account show`, role assignments, network, and CLI version |
| Shared Key-signed SAS denied | `allowSharedKeyAccess` is disabled for Blob Storage | Check account configuration; switch to user delegation SAS |
| Newly created SAS treated as not yet valid | `st` lies in the future due to clock skew | Omit `st` when unnecessary or add an appropriate buffer |
| Single-blob read SAS fails on container List | Only has `r` on blob, no `l` on container | Verify exact operation and signed resource |
| Valid SAS blocked by firewall | Storage firewall, private endpoint, `sip` IP filter, or DNS | Troubleshoot networking independently of signature and RBAC |
| URL breaks after copying into browser | Query string mis-encoded, truncated, `&` or `+` altered | Use URL builders/SDKs; never hand-edit tokens |
| Service SAS invalid after key rotation | Signed with the key that was just regenerated | Inventory and reissue SAS tokens per rotation plan |

### 10.1. Structured Troubleshooting Workflow

When downloading a blob with a SAS fails:

1. **Identify the SAS type:** user delegation, service, or account SAS; inspect parameter set without exposing the signature.
2. **Verify the target:** storage account, container, blob name, endpoint, HTTP method, and exact path.
3. **Verify timestamps:** was the request sent within `st`–`se` and before the delegation key expired?
4. **Verify permissions:** does `sp` allow the operation? For user delegation SAS, does the issuing principal hold matching RBAC/ACLs?
5. **Verify authorization mode:** does the account disallow Shared Key? Does the issuer have permission to request a user delegation key?
6. **Verify networking:** firewall, private endpoint, DNS, `sip`, HTTPS, and routing path.
7. **Inspect logs safely:** check error code, timestamp, request ID, and source IP; **never** paste full SAS URLs containing `sig` into logs or tickets.
8. **Apply minimal fix:** adjust the exact scope/permissions/expiry rather than re-enabling account keys or granting account-wide roles to silence an error.

You can use `x-ms-request-id` or diagnostic headers in responses to correlate with service logs. Configuring Storage diagnostic settings with appropriate retention helps trace both allowed and denied requests.

## 11. Secure Pattern for a Java Backend on Azure

Suppose a Java API runs on Azure App Service while Blob Storage holds customer documents:

```text
App Service (managed identity: mi-orders-api)
     |
     | Entra ID token + Storage Blob Delegator
     | + data permissions on invoices container
     v
Blob Storage: requests user delegation key
     |
     v
API generates SAS for one blob, Read permission, 10-minute TTL
     |
     v
API returns URL after verifying invoice ownership
     |
     v
Browser downloads over HTTPS directly from Storage
```

Separating responsibilities:

**The backend** authenticates the end user, maps the user to an invoice, selects the blob path, requests the key, and signs the SAS. **The managed identity** is the Azure workload's identity, not the invoice-downloading customer's identity. **Storage** validates the SAS attached to the request—it does not determine invoice ownership on the backend's behalf.

With the Azure SDK for Java, typical components include `DefaultAzureCredentialBuilder` or `ManagedIdentityCredentialBuilder` from `azure-identity` alongside `BlobServiceClientBuilder` and SAS builder classes in `azure-storage-blob`. Conceptual programming flow:

```text
credential = backend's Microsoft Entra credential
blobServiceClient = BlobServiceClient(endpoint, credential)
delegationKey = request time-limited user delegation key
blobClient = client referencing the exact container/blob
sasValues = Read permission + expiration time + HTTPS
sas = sign sasValues with delegationKey
return blob URL + "?" + sas after checking business permissions
```

This is **pseudocode**, not complete Java syntax. When implementing, use the exact SDK API for your version and pass expiry times and delegation keys with the proper data types. Do not hold delegation keys or SAS tokens longer than needed; avoid caching that could allow unintended token reuse.

If the backend **does not need to hand a temporary URL to a client** and only needs to read/write blobs itself, call the Blob Storage SDK directly with managed identity + RBAC. Generating a SAS in that case is unnecessary and only introduces another bearer credential to protect.

## 12. Security, Logging, and Operating SAS

### 12.1. Issuance Controls

SAS generation should be a controlled security capability with a clear owner:

- Only approved backends/identities may request delegation keys or access account keys.
- Every issuance request must undergo authentication and resource ownership verification.
- Enforce TTL, permission, and resource bounds server-side; never let clients request `d` or arbitrary lifetimes.
- If a SAS-issuing API is public-facing, rate-limit it to prevent abuse.
- Track the count and types of issued SAS tokens **in the issuing system**, because you cannot rely on Storage to list every ad hoc SAS ever minted.

### 12.2. Secure Token Transmission

- Enforce HTTPS only (`spr=https`).
- Never store SAS URLs in source code, Git, screenshots, dashboards, logs, or analytics tools.
- For web pages, configure policies to prevent URLs containing SAS tokens from leaking via Referer headers to external sites; consider `Referrer-Policy` and download handling.
- Never return a SAS to a client before checking permissions; never store long-lived tokens in local storage or public queues.
- Restrict `sip` when client IPs are static and compatible with the network topology. For mobile clients, NAT, or private endpoints, IP restrictions can cause unpredictable failures and must be tested.
- When tokens in URLs cannot be avoided, minimize lifetimes and prevent URL capture in observability pipelines.

### 12.3. Logging and Monitoring

Azure Storage can provide logs/metrics via Azure Monitor and diagnostic settings. During investigations, capture fields such as request ID, timestamp, endpoint, method, error code, and relevant network details. Never log the `sig` parameter or publish full query strings.

Audit questions to ask:

- Which systems hold **List Keys** or `generateUserDelegationKey/action`?
- Has the backend issued any SAS exceeding policy TTLs or carrying write/delete permissions?
- Is blob access spiking from unfamiliar source IPs or off-hours?
- Which flows still rely on Shared Key instead of Microsoft Entra ID?
- Are plans ready for rotating account keys and revoking user delegation keys during an incident?

Many storage accounts support a **SAS expiration policy** to monitor or enforce validity duration limits as configurable in the service; verify eligibility, SAS types, enforcement scope, and handling of `st` before enabling. An expiration policy does not replace backend authorization checks.

### 12.4. Cost Impact

Creating a SAS does not spin up a separate storage service tier, yet **Storage operations still incur charges** under the account's billing model: capacity, transactions, data reads/writes, and data transfer can all accrue. If an overly broad SAS is issued or leaked, unexpected request volume increases both risk and cost.

When proxying through a backend, App Service/Function compute and scaling must also bear the file-streaming load. When using a direct-download SAS URL, bandwidth flows straight from Storage to the client, though the bearer URL requires stricter safeguarding. Evaluate cost and security together rather than picking whichever option has fewer steps.

## 13. Common Misconceptions

**"A SAS is just a shorter form of the account key."** False. A SAS is a signed token with explicit access constraints. Service/account SAS tokens use the account key to *sign*, whereas a user delegation SAS uses a user delegation key.

**"Using a SAS means the recipient has to sign into Microsoft Entra ID."** False for standard SAS redemption. Anyone holding a valid SAS can send requests matching the signed conditions; Entra ID is used when minting a user delegation SAS, not required from the client downloading via SAS.

**"User delegation SAS works for Azure Files, Queue, and Table."** False. This type is for Blob Storage and compatible Data Lake Storage Gen2 scenarios. Other Storage services require their own supported authentication mechanisms.

**"You can immediately revoke any single individual SAS."** Not by default. Revocation depends on SAS type, stored access policies, signing keys, and blast radius. User delegation SAS does not support stored access policies.

**"Assigning Storage Blob Data Reader on a container is enough to request a user delegation key."** Not necessarily. You also need `generateUserDelegationKey/action` at the storage account or parent scope.

**"Changing an RBAC role instantly invalidates all previously issued SAS tokens."** Do not assume so. Issued tokens and delegation keys have their own lifetimes; plan around short expiration or revoking delegation keys.

**"Using user delegation SAS means no need to check which customer owns an invoice."** False. Application authorization must still verify the recipient is entitled to access the blob before minting the URL.

**"Disabling Shared Key blocks user delegation SAS too."** For Blob Storage, no: user delegation SAS is signed using Entra ID and a user delegation key; verify permissions and other conditions. Still, inventory impacts on related services/applications before toggling the account setting.

## 14. Practice Exercises and Design Scenarios

### Scenario A: Customer Downloading an Invoice

An ordering app needs to let customers download one PDF for 10 minutes without allowing container listing or blob deletion.

Propose:

1. Direct account key, service SAS, or user delegation SAS?
2. Who is authenticated before issuing the token?
3. What values should resource, `sp`, `se`, and `spr` take?
4. At which scope should RBAC be assigned to the issuing principal?
5. If a URL leaks with 3 minutes remaining, how should the system respond?

**Guidance:** prefer a user delegation SAS with `sp=r`, exact blob resource, HTTPS, and a 10-minute TTL. The API authenticates the customer and verifies invoice ownership before signing. The API's managed identity needs delegation-key permission at the account scope and data read permission on the target container. On a leak, weigh severity: a short TTL limits exposure; if emergency revocation is required, evaluate revoking delegation keys since it can affect other SAS tokens.

### Scenario B: Partner Uploading Documents

A partner needs to upload one file into corporate storage within a limited window. Security does not want the partner reading or listing other files.

Consider:

- Minimum permissions to create/write to the target per actual Blob API behavior, without granting Delete/List by default.
- Server-assigned blob name to avoid overwriting existing files.
- TTL and file size; whether block/chunked upload is needed.
- CORS if the client is a browser; CORS is **not** an authorization mechanism replacing SAS.
- Content scanning, format validation, metadata, and post-upload processing workflow.
- Whether issuing a SAS or proxying uploads through the backend provides tighter control.

Never issue `sp=w` across an entire container for days just to receive one file. Once uploaded, the backend must validate results and inspect data before admitting it into business workflows.

### Scenario C: Legacy System Using Account Keys

An ETL pipeline and two applications still use Shared Key; the security team wants to set `allowSharedKeyAccess=false` for Blob Storage.

Outline a migration plan:

1. Inventory all systems/SDKs and all account-key-signed SAS tokens.
2. Categorize backend-to-Storage flows to migrate to Entra ID + RBAC.
3. Categorize file-sharing flows to migrate to user delegation SAS.
4. Check impact on Azure Files or other Storage features in active use.
5. Test in non-production, monitor logs/metrics, prepare rollback.
6. Apply the change under change approval and confirm legacy flows no longer depend on keys.

## 15. Self-Check Questions

**1. How does Shared Key differ from a SAS?** Shared Key uses a broadly privileged storage account key to authenticate requests; a SAS is a signed token with declared scope, permissions, and lifetime.

**2. Which two SAS types use the account key for signing?** Service SAS and account SAS.

**3. Which service is user delegation SAS designed for?** Azure Blob Storage, including supported Data Lake Storage Gen2 scenarios.

**4. Why check `generateUserDelegationKey/action`?** Because it is the permission allowing an Entra principal to request a delegation key at the Blob service/storage account level, independent of blob read permissions.

**5. Can a user delegation key last indefinitely?** No; its maximum lifetime is 7 days, and a SAS signed with it cannot exceed the key's lifetime.

**6. Can a stored access policy be used with an account SAS or user delegation SAS?** No; this mechanism is for eligible service SAS tokens.

**7. Does holding a SAS URL prove the recipient has business authorization to the file?** No. The backend must verify permissions prior to issuing it.

**8. Before blocking Shared Key on Blob Storage, what must be done first?** Inventory dependencies, migrate clients to Entra ID/user delegation SAS, test thoroughly, and prepare an incident/rollback plan.

## 16. Production Deployment Checklist

- [ ] Chosen the right mechanism—direct Entra ID, user delegation SAS, service SAS, or account SAS—based on real requirements.
- [ ] Kept storage account keys and key-bearing connection strings out of frontends and repositories.
- [ ] Backend authenticates users and checks business authorization before issuing any SAS.
- [ ] SAS grants only the necessary resource, permissions, TTL, and protocol.
- [ ] For user delegation SAS, the principal has key-request rights at the right account scope and data rights at the narrowest scope.
- [ ] Avoided stored access policies for user delegation/account SAS.
- [ ] Accounted for clock skew, RBAC propagation delay, and DNS/firewall/private endpoint differences.
- [ ] Established procedures for inventorying, revoking, rotating account keys, and revoking delegation keys when needed.
- [ ] Prevented logging query strings/tokens, enforced HTTPS, and ensured secure URL transmission.
- [ ] Assessed risks of `allowSharedKeyAccess=false` and impacted integrated services.
- [ ] Configured metrics/logs, anomalous download monitoring, and transaction/bandwidth cost tracking.
- [ ] Tested authorized, unauthorized, expired, malformed URL, and network-blocked scenarios.

## Conclusion

**Shared Key** is an authentication mechanism using a broadly privileged Storage account key; a **Shared Access Signature** is a signed token delegating constrained actions, scope, and lifetime. **Service SAS** and **account SAS** are signed with the account key, whereas a **user delegation SAS** for Blob Storage uses a delegation key issued on top of Microsoft Entra ID, eliminating the backend's need to hold account keys.

For modern Azure applications, prefer **managed identity + Azure RBAC** for backend-to-Storage connections; when clients need temporary access to download a blob, prefer a **user delegation SAS** with minimal permissions and a short lifetime. Always pair SAS with business authorization checks, URL protection, network restrictions, safe logging, and a revocation plan matching the signature type in use.

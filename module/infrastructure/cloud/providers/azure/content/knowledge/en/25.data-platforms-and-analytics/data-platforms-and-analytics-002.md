# Hierarchical Namespace, ACLs, and Data Authorization

> **Chapter:** Data Platforms and Analytics  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute, storage, and data services. Learn how to deploy, monitor, protect, and control costs for an application architecture on Azure.

## Lesson Objectives

After completing this lesson, you will be able to:

1. Explain what **Hierarchical Namespace (HNS)** is, why it matters for **Azure Data Lake Storage Gen2 (ADLS Gen2)**, and how it differs from emulating folders via blob names.
2. Design the **storage account → file system/container → directory → file** hierarchy for landing, curated, and analytics data flows.
3. Read, configure, and inspect **POSIX-like access ACLs** and **default ACLs**, including `r`, `w`, `x` permissions, owner, owning group, named user/group, mask, and other.
4. Distinguish between **Azure RBAC data roles**, management-plane roles, and **path-level ACLs**, especially when both RBAC and ACLs coexist.
5. Evaluate effective permissions when traversing multiple directories, checking behaviors for creating, reading, writing, listing, renaming, and deleting an object.
6. Use the Azure Portal, **Azure CLI**, and **Python Azure Storage Data Lake SDK** to verify HNS, inspect ACLs, grant lab permissions, and test negative cases.
7. Design permissions for data engineers, ingestion services, analysts, and auditors using Microsoft Entra groups/managed identities.
8. Combine ACLs with **Private Endpoints, TLS, Shared Key policy, SAS, encryption, auditing, and lifecycle** to protect data.
9. Diagnose 403 errors, missing `x` permissions, ACL masks, overly broad RBAC, wrong tokens/identities, DFS/Blob paths, and permission drift.
10. Build a runbook, periodic checks, and rollback plan for production data environments.

## 1. Context: A Multi-Team Data Lake

A company collects order data, payment reconciliations, and application logs on Azure for analytics. Multiple teams share the same storage account:

- **Ingestion service** writes source files into `landing`.
- **Data engineer** cleanses, standardizes, and moves data to `curated`.
- **Finance analyst** only reads vetted datasets under the finance branch.
- **BI/reporting** reads aggregated datasets without modifying source files.
- **Auditor** inspects data within an approved scope; cannot write or delete.
- **Platform administrator** manages the account, networking, observability, and permission changes.

If every group receives `Storage Blob Data Contributor` across the **entire storage account**, accidental edits/deletions or out-of-scope reads become easy. If only blob names with `/` characters are used, directory operations such as renaming, per-directory ACL administration, and moving data may not share the semantics of a true hierarchy.

**Azure Data Lake Storage Gen2** is an analytics data storage model built on **Azure Blob Storage with Hierarchical Namespace enabled**. HNS makes directories real entities in the namespace, supporting directory operations and **fine-grained path-level ACLs** within supported boundaries.

~~~mermaid
flowchart TB
    ACC["Storage account\nHNS enabled"]
    FS["File system: lake"]
    LAND["landing/\nRaw ingest"]
    CUR["curated/\nValidated datasets"]
    FIN["curated/finance/\nFinance data"]
    SALES["curated/sales/\nSales data"]
    ANA["analytics/\nShared aggregates"]
    ING["Ingestion identity"]
    ENG["Data engineer group"]
    FUSER["Finance analyst group"]
    BI["BI service"]
    ACC --> FS
    FS --> LAND
    FS --> CUR
    CUR --> FIN
    CUR --> SALES
    FS --> ANA
    ING -.->|"Write via ACL"| LAND
    ENG -.->|"Read/write selected paths"| CUR
    FUSER -.->|"Read only"| FIN
    BI -.->|"Read only"| ANA
~~~

**This diagram shows only the target authorization design**; Azure does not automatically grant these permissions when creating a storage account. RBAC, access ACLs, default ACLs, networking, and identities must be configured and tested separately.

### 1.1. Two Mandatory Design Questions

1. **Who is allowed to do what on the data?** Separate data-plane RBAC, ACLs, and user/application identities.
2. **From where are connections allowed?** Use firewalls, Private Endpoints, Private DNS, and transport policies; valid data permissions can still be blocked by networking.

A secure solution must answer **both**. HNS/ACLs do not replace private networking, key management, or application-level controls for sensitive data.

## 2. How Does Hierarchical Namespace Work?

### 2.1. Flat Blobs vs. a True Hierarchy

With a flat Blob Storage namespace, blob names might look like:

~~~text
raw/2026/11/20/orders-01.parquet
raw/2026/11/20/orders-02.parquet
~~~

The `/` characters in the name help tools display virtual "folders." However, the storage layout of a flat blob namespace does not mean each segment `raw`, `2026`, `11`, `20` is a directory object with its own ACL.

When **HNS is enabled**, the service provides directory semantics:

~~~text
Storage account: stlakeprod001
  File system (= Blob container): lake
    /landing/
      /orders/
        /2026/
          /11/
            /orders-01.parquet
    /curated/
      /finance/
        /orders.parquet
      /sales/
        /revenue.parquet
    /analytics/
      /daily/
        /sales_summary.parquet
~~~

The `curated/finance` directory is a real hierarchical path with an owner, group, and ACLs controlling operations. HNS supports file-system-oriented operations like **rename/move within the namespace** per service capabilities, aiding data processing engines that rename directories when committing results.

### 2.2. Benefits for Spark and Data Platforms

In a data pipeline, a Spark job can:

1. Write data to a staging directory `/tmp/job-42`.
2. Validate data, schema, and row counts.
3. Rename/move the directory to `/curated/orders/day=2026-11-20` per an appropriate commit strategy.
4. Allow the analytics team to read the new directory via ACLs.

With a hierarchical system, directory operations differ in semantics and performance from listing and copying thousands of blobs that emulate a folder. However, **atomic rename is not a multi-container or multi-system ACID transaction**. Never assume renaming a directory automatically commits across Azure SQL, Cosmos DB, and Event Hubs.

### 2.3. Resource Structure

| Concept | ADLS Gen2 with HNS | Meaning |
| --- | --- | --- |
| Storage account | HNS-enabled Azure Storage account | Configures region, replication, networking, keys |
| File system | Blob container | Governed data root within the account |
| Directory | Hierarchical path object | Has owner/group and ACLs |
| File | File within a file system | Has owner/group and ACLs |
| Path | Sequence of segments from root to file | Used to evaluate tree traversal permissions |
| Access ACL | Permissions on the current object | Evaluated when operating on a path |
| Default ACL | Permission template for new child objects | Exists only on directories; does not modify retroactively |
| Azure RBAC | Role assignment at a resource scope | Can grant data access independently of ACLs |

### 2.4. DFS Endpoint and Blob Endpoint

An HNS-enabled account can expose these endpoints:

~~~text
https://stlakeprod001.dfs.core.windows.net/
https://stlakeprod001.blob.core.windows.net/
~~~

- **DFS endpoint** serves Data Lake Storage Gen2 filesystem/path operations and ACLs.
- **Blob endpoint** serves supported Blob APIs/clients.
- A file system corresponds to a Blob container, **not two separate copies of data**.
- Check API/SDK compatibility and HNS features; do not assume every Blob API behaves identically to a flat namespace.
- With **Private Endpoints**, appropriate Private Endpoints and Private DNS may be required for **both blob and dfs subresources** when workflows perform operations or redirects across both endpoints. Never conclude "DFS is private so Blob must be private."

### 2.5. HNS Limitations to Account for Early

- **Not every account/storage configuration supports enabling HNS or all Blob features.** Check eligibility, SKUs, feature matrices, and migration constraints.
- **Enabling HNS can be a decision not easily reversed by flipping a simple flag.** Review supported procedures and test compatibility before applying to accounts with existing data.
- Billing, operations, features, lifecycle, and management tools can differ between HNS enabled and disabled.
- Do not treat HNS as a relational database or a 100% POSIX filesystem: it is object storage with provided file-system semantics, requiring review of the API scope.

## 3. Organizing a Data Lake by Data Layers

### 3.1. Sample Data Tree

~~~text
lake/
  landing/
    orders/
      yyyy=2026/mm=11/dd=20/
    payments/
      yyyy=2026/mm=11/dd=20/
  quarantined/
    invalid/
  curated/
    finance/
      invoices/
      reconciliations/
    sales/
      orders/
      customers/
  analytics/
    dashboards/
    machine-learning/
  tmp/
    pipeline-runs/
~~~

**Goal:** prevent report consumers from modifying raw ingest; allow data engineers to process `curated`; allow the finance team to read only the finance branch. Maintain a dedicated `quarantined` zone for invalid data; avoid exposing unvetted data to all analysts.

### 3.2. Using Containers vs. Directories for Boundaries

| Criterion | Separate File Systems/Containers | Single File System, Multiple Directories |
| --- | --- | --- |
| Azure RBAC scope | Easy to assign roles per container | Cannot assign RBAC roles directly to every folder like containers |
| Fine-grained path ACL | Supported | Key strength |
| Network/account boundary | Same account still shares many policies | Same account |
| Lifecycle, workload ownership | Easy to organize per container with available policies | Requires ACL/IaC and naming standards |
| Security audit | Simpler with clear ownership | Many ACEs/paths to audit for drift |
| Strict tenant isolation | May require separate accounts/containers | Directory ACLs may be insufficient per threat model |
| Application behavior | URIs may change when separated | Data in one filesystem, multiple paths |

Do not use **directory ACLs** as an isolation mechanism for a workload granted **data-plane Contributor at the account scope**: the broad role can render restrictive ACLs ineffective for holders of that role.

### 3.3. Naming and Path Conventions

- Use clear, purposeful names: `landing/orders`, `curated/finance`.
- Avoid names containing personal information or access tokens.
- Separate `dev/staging/prod` via accounts or sufficiently isolated environments per policy.
- For partition-style paths like `year=2026/month=11`, factor in directory/file counts, query engine metadata scans, and operation costs.
- Never use `other::rwx` as a quick fix for access errors.
- Assign an owner group and retention/archival policy to each dataset.

## 4. Access ACLs and Default ACLs

### 4.1. Access ACL: Permissions on Existing Objects

An **Access ACL** is a set of Access Control Entries (ACEs) on an **existing directory or file**, for example:

~~~text
user::rwx
user:<analyst-object-id>:r-x
group::r-x
group:<engineer-group-object-id>:rwx
mask::rwx
other::---
~~~

This is the ACL of a **directory**: the named analyst can read/traverse, the named engineer group can create/modify entries per effective permissions, and `other` has no access.

**GUIDs inside angle brackets `<>` are placeholders**; implementers must substitute real, verified **Microsoft Entra object IDs** for supported users/groups/service principals rather than arbitrary display names or emails.

### 4.2. Default ACL: Inheritance Template for New Children

**Default ACLs can only be set on directories.** Example on `/curated/finance`:

~~~text
default:user::rwx
default:group::r-x
default:group:<finance-readers-group-object-id>:r-x
default:mask::r-x
default:other::---
~~~

When a file or directory is created underneath, the new object's ACL is derived from the parent default ACL per the service's inheritance rules; **not every default permission becomes an effective access right if masks or creation semantics constrain it**.

For a **new directory**, the default ACL can continue to be inherited by subsequent generations of children. For a **file**, there is no default ACL for children because files do not contain child objects.

### 4.3. Comparing the Two ACL Types

| Question | Access ACL | Default ACL |
| --- | --- | --- |
| Set on files? | Yes | No |
| Set on directories? | Yes | Yes |
| Controls operations on the current object? | Yes | Not directly |
| Do existing children change automatically when modified? | No | No |
| Can new children inherit permissions from here? | Not an inheritance template | Yes, per service rules |
| Guarantees current owner permissions? | Check access ACL and ownership | Must inspect current ACL separately |
| Suitable for new pipeline-created paths? | Permissions on current path | Template for future files/folders |

**Common mistake:** adding `default:group:finance-readers:r-x` while forgetting the **access ACL on the current directory**, leaving Finance unable to enter the parent.

### 4.4. Access ACLs Are Not the Entire Authorization Story

When requests use **Microsoft Entra authorization**, the service evaluates access based on **RBAC data actions and ACLs** according to ADLS Gen2 rules. A **sufficiently broad** RBAC data role can allow operations even when access ACLs are restrictive. Once a request is authorized via RBAC, ACLs are not necessarily evaluated as an additional restriction step.

Therefore:

- Do not grant `Storage Blob Data Contributor` at the account scope to a user and expect `other::---` to prevent them from writing to another branch.
- If choosing ACLs as the **granular restriction mechanism**, audit all RBAC data grants for the principal at account/container/ancestor scopes.
- Account keys/SAS have distinct authorization semantics: never assume POSIX ACLs constrain a client using a powerful key.

## 5. Meaning of `r`, `w`, `x` on Directories and Files

### 5.1. Permissions on Files

| Character | For a File in ADLS Gen2 | Example |
| --- | --- | --- |
| `r` | Read file contents | Analyzing a Parquet file |
| `w` | Write/modify file contents per supported APIs | Pipeline updating a file |
| `x` | Does not mean executing a binary as in standard Linux OSs | Do not use `x` to run binaries in a data lake |

### 5.2. Permissions on Directories

| Directory Permission | Practical Meaning |
| --- | --- |
| `r` | Read the list of entries in the directory when other conditions also permit |
| `w` | Create/delete/modify entries in the directory when paired with `x` and other required conditions |
| `x` | **Traverse/search**: pass through the directory to access a child object when the path is known |
| `r-x` | List and enter the folder; cannot create/delete entries |
| `-wx` | Can create/delete entries when prerequisites are met, but cannot list all entries |
| `--x` | Traverse a known path; insufficient to list the directory |
| `r--` | Cannot usefully access children due to missing `x` |
| `rwx` | Read/list, traverse, and modify entries in the directory |
| `---` | No ACL permissions on the directory |

When **reading a file by path**, the identity must be able to traverse every parent directory via `x` and hold `r` on the target file, unless another authorization mechanism grants sufficient permission.

### 5.3. Detailed Traversal Example

File:

~~~text
/lake/curated/finance/2026/invoices.parquet
~~~

For a user relying solely on ACLs, the checks evaluated are:

~~~text
/                    require x
/curated             require x
/curated/finance     require x
/curated/finance/2026 require x
/invoices.parquet    require r
~~~

To **list** the `/curated/finance/2026` folder, both `r` and `x` are needed on that folder, plus `x` on ancestors as applicable. Knowing the exact path, a user can read the file with `x` on parent directories and `r` on the file **without being able to list all sibling files**.

### 5.4. Creating and Deleting Files

- To **create a child entry** in a directory, `w+x` on the parent plus traversal permissions on ancestors are typically required.
- To **delete or rename an entry** in a directory, directory permissions (typically `w+x` on the parent) are critical; do not assume having `w` on the target file suffices.
- Having `r` on a file does not permit deleting the entry.
- Having `w` on a file may permit modifying contents, but does not grant permission to read contents or list the folder.
- Directory rename/move operations, ownership, leases, immutability policies, or API-specific limitations may impose extra constraints. Test the exact operation you intend to run.

**Security note:** a user with `w+x` on the parent can delete a child entry even if the ACL on the file itself does not grant `w`, according to supported directory semantics. Therefore, never grant `w` on a "report reading" folder simply because users need to upload files in a separate branch.

## 6. Components of an ACL Entry

### 6.1. Base Entries

A typical ACL includes:

~~~text
user::rwx       # owner of path
group::r-x      # owning group
other::---      # identities not otherwise matched
~~~

Here `user::` does not mean "every user"; it means the **owning user**. Similarly, `group::` is the **owning group**. `other::` is the fallback for identities not matched by more specific entries.

### 6.2. Named User and Named Group

~~~text
user:<principal-object-id>:r--
group:<finance-group-object-id>:r-x
~~~

These entries grant permissions to a specific user/group without changing current ownership. For stable governance, assign to **Microsoft Entra security groups** with clear ownership rather than individual users when managing team permissions.

### 6.3. Mask: Granted Permissions Can Be Masked Down

The mask is an upper bound on effective permissions for **named users, named groups, and the owning group class**. The mask normally **does not constrain the owning user or other** in the POSIX ACL model.

Example:

~~~text
user::rwx
user:<analyst-oid>:rwx
group::r-x
mask::r-x
other::---
~~~

The analyst has an `rwx` entry, yet their **effective ACL permission** is capped at `r-x` because the mask lacks `w`. A user might inspect the ACL, see `rwx` next to a named user entry, and still be denied write operations.

Second example:

~~~text
group:<etl-group-oid>:rwx
mask::r--
~~~

The ETL group is effectively capped at `r--`. On a directory, lacking `x` can cause even reading objects inside by path to fail. **Do not fix this by granting account-wide data-plane Owner**; recalculate the access ACL/mask to match the intended permissions.

### 6.4. Effective Permissions Are Not Arbitrary Addition

In POSIX-style ACLs, evaluation order across identity/owner, named user, group class, and other follows specific rules. Do not assume every matching ACE combines via an "unconditional union of all `rwx` bits," nor that a separate deny ACL can override RBAC.

In ADLS Gen2 ACLs, **there is no general POSIX deny ACE** like some NTFS ACLs; `other::---` is not a deny override against higher permissions granted by RBAC.

### 6.5. ACL Owner and Permission to Change ACLs

- The **owning user** of a path and principals with **appropriate ACL management permissions** (e.g., a supported privileged role/data action) can manage ACLs per service capabilities.
- Having `rwx` on a directory **does not automatically mean** you can edit ACLs or ownership on all child objects.
- **Storage Blob Data Owner** is a privileged data-plane role suited for approved operators managing ACLs; do not grant it to routine ingestion jobs.
- Changing owner/group may require dedicated permissions and alters security boundaries; it must be audited.

In practice, owner/owning group may be set at object creation time and differ from the business owner group listed in a runbook. Always inspect the actual owner rather than inferring from folder names.

## 7. Default ACLs and Inheritance Across the Data Tree

### 7.1. How Do New Files Receive Permissions?

Suppose directory `/curated/finance` has an access ACL for ETL and a default ACL for Finance readers. When ETL creates `q4.csv`:

~~~text
/curated/finance/
  [access ACL]  current
  [default ACL] permission template for children

/curated/finance/q4.csv
  [access ACL]  determined at creation from inheritance rules
~~~

**Permissions on a new file** can be derived from the parent directory's default ACL according to file creation rules and the mask, but verify the actual result using `get-access-control` / `az storage fs access show`. A file does not receive a default ACL for grandchildren.

### 7.2. New Subdirectories Receive Both ACL Types

A new directory such as `/curated/finance/2026` can receive:

- **Access ACL** governing the child directory itself.
- **Default ACL** continuing as a template for new files/subdirectories inside it.

Structure:

~~~text
/curated/finance        default group:finance-readers:r-x
  /2026                 access / default inherited by rules
    /11                 access / default inherited by rules
      report.parquet     access inherited by rules
~~~

If multiple services create files in the system, test end-to-end so directories do not end up with unintended default ACLs.

### 7.3. Updating a Default ACL Does Not Update Old Data

This is a common administrative mistake:

1. `/curated/finance/old-report.parquet` is created initially.
2. Later, a default ACL for `finance-readers` is added on the parent.
3. Finance users still cannot read `old-report.parquet`.

**This is expected behavior**: default ACLs primarily affect **newly created objects**, not existing ones retroactively. To update old data, run an ACL update operation on existing paths, using a recursive operation only after **assessing its risk**.

### 7.4. Safer Directory Configuration Pattern

Logical example:

~~~text
/curated/finance/
  Access ACL:
    user::rwx
    group::r-x
    group:<finance-readers-oid>:r-x
    mask::r-x
    other::---

  Default ACL:
    default:user::rwx
    default:group::r-x
    default:group:<finance-readers-oid>:r-x
    default:mask::r-x
    default:other::---
~~~

**You must grant `x` on parent directories** of `/curated/finance` for the appropriate group, potentially `--x` if you do not wish to allow listing the entire tree. On new files, default permissions apply per file creation semantics; avoid assuming `x` on a file means program execution.


## 8. Azure RBAC and ACLs: Two Mechanisms to Understand Together

### 8.1. Azure RBAC by Resource Scope

Microsoft Entra ID authenticates the principal; **Azure RBAC** assigns roles at the subscription, resource group, storage account, or Blob container/file system and other supported scopes.

| Azure Role | Primary Meaning | Notes |
| --- | --- | --- |
| **Storage Blob Data Reader** | Read blob data within role scope | May be broader than an ACL branch |
| **Storage Blob Data Contributor** | Read/write/delete blob data within role scope | Unsuitable for analysts who only read one folder |
| **Storage Blob Data Owner** | Broad data privileges and ability to manage ACLs | Grant only to approved operators |
| **Storage Blob Data Delegator** | Permissions related to user delegation keys | Does not automatically grant file read/write |
| **Reader** (management plane) | View resource metadata | Not directly a Data Reader |
| **Contributor** (management plane) | Manage multiple Azure resources | Can retrieve account keys if policy/role permits |
| **Owner** (management plane) | Very broad management and role assignment rights | Requires privileged governance |

**Control-plane Contributor does not directly equate to Data Contributor when an app uses Entra tokens**, but if a principal has `listKeys`, they can retrieve Shared Keys and access data whenever the Storage account allows key authorization. Evaluate all access paths.

### 8.2. Path-Level ACLs

ACLs refine permissions on:

~~~text
lake/curated/finance/
lake/curated/sales/
lake/analytics/daily/
~~~

If the Finance team only needs to read `finance`, grant ACLs on that branch plus traversal on ancestors; do not grant `Storage Blob Data Reader` across the entire account if they must not read `sales`.

### 8.3. The RBAC–ACL Relationship

For a Microsoft Entra-authenticated data-plane request on an HNS-enabled account:

1. Evaluate authentication, networking, and relevant service policies.
2. If **RBAC data actions** at the resource scope already permit the operation, a restrictive path ACL **does not necessarily block the request**.
3. If RBAC does not grant sufficient data permission, ACLs are evaluated to permit the operation based on owner/group/named entries and mask.
4. Shared Key/SAS authorization has different semantics; do not apply this diagram as a universal algorithm for every credential type.

~~~mermaid
flowchart TD
    REQ["Entra-authenticated data request"]
    NET{"Network and auth OK?"}
    RB{"RBAC data actions\npermit operation?"}
    ACL{"Path ACL and\ntraversal permit?"}
    YES["Allow"]
    NO["Deny"]
    REQ --> NET
    NET -->|"No"| NO
    NET -->|"Yes"| RB
    RB -->|"Yes"| YES
    RB -->|"No"| ACL
    ACL -->|"Yes"| YES
    ACL -->|"No"| NO
~~~

**ACLs have no deny ACE capable of overriding a broad RBAC data role.** For instance, `other::---` on `curated/sales` does not prevent a principal holding `Storage Blob Data Contributor` at the account scope from accessing data permitted by that role.

### 8.4. Three Ways to Draw Boundaries

- **Azure RBAC** when an entire container/account forms one trust boundary.
- **ACLs** when multiple teams share a file system but need directory/file restrictions.
- **Separate accounts or containers** when strict isolation, distinct region/network policies, billing ownership, or independent data lifecycles are needed.

One user may belong to multiple groups, use multiple credentials, or hold inherited RBAC roles. To know effective permissions, inspect **all grant paths** and test with the real identity.

## 9. Entra Groups and Managed Identities for a Data Lake

### 9.1. Human and Service Access

- Data engineer users via Azure Storage Explorer.
- Managed identity of ETL compute/analytics services.
- Workload identity of AKS/Container Apps.
- Service principal of CI/CD pipelines.
- Microsoft Entra security groups for Finance, BI, and Auditors.

ACL named users/groups typically reference an **Entra object ID GUID**, not a display name. When a command asks for a `principal ID`, do not pass an app registration client ID instead of the object ID without verifying.

### 9.2. Functional Group Matrix

| Identity/Group | Required Data | Recommended Permissions |
| --- | --- | --- |
| `grp-lake-ingestion` | `landing/orders` | Create and write files |
| `grp-lake-engineers` | `landing`, `curated` | Read landing, read/write curated |
| `grp-lake-finance` | `curated/finance` | Read-only |
| `grp-lake-bi` | `analytics` | Read-only |
| `grp-lake-auditors` | Approved branches | Read-only |
| `mi-etl-prod` | Specific pipeline paths | Runtime least privilege |
| `grp-lake-acl-admins` | ACL administration | Audited data-owner/ACL privilege |

Assigning permissions via groups avoids editing ACLs across thousands of files when staff change teams. However, this requires **group owners, membership reviews, and an approval workflow**; an unreviewed addition to the Finance group can unexpectedly expand access.

### 9.3. Do Not Mix Administrative and Runtime Identities

An ETL runtime usually does not need account-wide `Storage Blob Data Owner`. When bulk ACL re-application is required, use an operator or temporary elevated identity with administrative permissions, a change ticket, and logs; never hand out long-lived Shared Keys to notebooks just to "make it work."

### 9.4. Token Refresh and Membership

When a new role/group is granted, permissions may require propagation time or a token refresh. Verify the exact principal, group object ID, token, and account policy before altering ACLs. **Never test with a Platform Admin account and conclude that a pipeline's runtime identity has the same permissions.**

## 10. Shared Key, SAS, and the Risk of Bypassing ACLs

### 10.1. Shared Key Authorization

Storage account keys are shared secrets granting broad data access. Requests signed with a Shared Key **do not behave like Entra user access governed by POSIX ACLs**. Restricting a group via ACLs is insufficient if workloads still hold the account key.

### 10.2. How Is SAS Authorized?

- **Account SAS/service SAS** are typically based on the account key and signed scope/permissions/expiry.
- **User delegation SAS** is based on Entra authorization and a user delegation key per supported API capabilities.
- A SAS URI is a bearer credential; restrict its scope, lifetime, and store it securely.

Avoid blanket statements like "all SAS bypass ACLs" or "all SAS are bounded by ACLs"; evaluate the SAS type, API, permissions, and signing model.

### 10.3. Policy Restricting Shared Key

Some Azure Storage configurations expose the `allowSharedKeyAccess` (Allow storage account key access) property. Disabling Shared Key can impact applications using connection strings, account/service SAS, and legacy tools.

Procedure:

1. Inventory key-based workloads and automation.
2. Test Entra OAuth in SDKs/tools.
3. Assign sufficient—not overly broad—roles/ACLs.
4. Test user delegation SAS if applications require SAS.
5. Toggle the policy in staging, monitoring 401/403 errors and performance.
6. Obtain approval and prepare a rollback plan before applying to production.

Never disable Shared Key on a live account merely to "test ACLs," as it can break unrelated pipelines.

## 11. Read-Only Preflight: Inspecting HNS and ACLs with Azure CLI

### 11.1. Preparation

- Authorized subscription/resource group/storage account.
- HNS enabled and file system `lake` exists.
- CLI version supporting `az storage fs` and `--auth-mode login`.
- Identity has metadata read permissions and a network path to the DFS endpoint.
- Never print account keys to a terminal or chat for debugging.

### 11.2. Reading HNS Configuration

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-data-lake-lab"
STORAGE="stlakeunique001"
FILESYSTEM="lake"

az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query "{name:name, kind:kind, sku:sku, hns:isHnsEnabled, allowSharedKey:allowSharedKeyAccess, publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

If `hns: false`, **do not** proceed under the assumption that Data Lake filesystem ACLs are active. Enabling HNS on an account with existing data carries eligibility, compatibility, and potential irreversibility constraints; it requires a dedicated migration plan.

### 11.3. Listing File Systems

~~~bash
az storage fs list \
  --account-name "$STORAGE" \
  --auth-mode login \
  --output table
~~~

`--auth-mode login` uses the CLI's Entra identity rather than silently fetching account keys. Permission to **list containers** can differ from permission to read a file at a known path; do not conclude from a list error that all path ACLs are wrong.

### 11.4. Reading Path ACLs

~~~bash
az storage fs access show \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "curated/finance" \
  --auth-mode login \
  --output json
~~~

Output may include owner/group/ACL permissions. If it fails, check path existence, parent traversal, RBAC/ACL, and networking. To inspect root or parent paths, check `az storage fs access show --help` for your CLI version rather than assuming every version uses the same root path syntax.

### 11.5. Reading Azure RBAC Assignments

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query id --output tsv)

az role assignment list \
  --scope "$STORAGE_ID" \
  --include-inherited \
  --output table
~~~

This is a read-only command. Also review assignments at **container scope**, management ancestors, and relevant group memberships; an account-scope snapshot alone is not a complete effective-permission audit.

### 11.6. Minimum Verification Checklist

| Check | Evidence |
| --- | --- |
| Azure context | Correct subscription/tenant and identity |
| HNS state | `isHnsEnabled=true` |
| Shared Key policy | Whether key access could bypass ACL intent |
| DFS endpoint/network | Appropriate DNS, TLS, and routing |
| Access ACL | Owner, named entries, mask, and other |
| Default ACL | Set on intended directories |
| Parent traversal | Identity has `x` on every ancestor |
| Data-plane RBAC | No overly broad inherited roles |
| Negative test | Read-only user cannot write/delete |


## 12. Controlled ACL Writes with Azure CLI

### 12.1. Never Test on the Production Root

**The commands in this section modify data paths and security.** Practice only in an isolated, approved file system or lab branch. Never run `set` or `set-recursive` on a production data lake root, as a single mistake can sever access for many pipelines and users.

When manipulating ACLs via CLI, verify the CLI version, executing identity, and supported ACL modification capabilities:

~~~bash
az storage fs directory create --help
az storage fs access show --help
az storage fs access set --help
az storage fs access update --help
~~~

### 12.2. Creating a Lab Directory

~~~bash
RG="rg-data-lake-lab"
STORAGE="stlakeunique001"
FILESYSTEM="lake"

az storage fs directory create \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --name "acl-lab" \
  --auth-mode login

az storage fs directory create \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --name "acl-lab/finance" \
  --auth-mode login
~~~

Appropriate authorization is required on the path's parent (typically `w+x` via ACL, or data permission via RBAC). The `acl-lab` path is a test environment, not an alias for production `curated/finance`.

### 12.3. Preparing the Group Object ID

~~~bash
FINANCE_GROUP_ID="<ENTRA_FINANCE_GROUP_OBJECT_ID>"
~~~

The placeholder must be replaced with a **real GUID** obtained from a verified Entra group object ID; do not use a client ID or display name. There is no need to dump the entire Entra user directory for a small exercise.

### 12.4. Setting Access ACL on a Lab Directory

~~~bash
# WRITE ACL: the set command can replace the current ACL!
az storage fs access set \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "acl-lab/finance" \
  --acl "user::rwx,group::r-x,group:$FINANCE_GROUP_ID:r-x,mask::r-x,other::---" \
  --auth-mode login
~~~

This is a **complete ACL string for the lab directory**. On an existing production directory, never run `set` just to add one group and inadvertently wipe out existing named users/groups. Consider `update` if the API supports merging ACEs per configuration, and always save a baseline before making changes.

`user::rwx` grants permissions to the **owning user**, not necessarily the CLI principal running the command.

### 12.5. Access ACL and Default ACL on the Same Directory

A directory can carry both layers:

~~~text
Access entries:
  user::rwx
  group::r-x
  group:<finance-group-id>:r-x
  mask::r-x
  other::---

Default entries:
  default:user::rwx
  default:group::r-x
  default:group:<finance-group-id>:r-x
  default:mask::r-x
  default:other::---
~~~

Example when the CLI version supports an ACL string containing both ACE types:

~~~bash
# Only inside the prepared lab directory.
az storage fs access set \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "acl-lab/finance" \
  --acl "user::rwx,group::r-x,group:$FINANCE_GROUP_ID:r-x,mask::r-x,other::---,default:user::rwx,default:group::r-x,default:group:$FINANCE_GROUP_ID:r-x,default:mask::r-x,default:other::---" \
  --auth-mode login
~~~

Because `set` can **replace the entire ACL** and behavior can vary across CLI versions, check `--help`, read back the ACL, and test with a new directory/file. If the command fails with parse or authorization errors, halt testing rather than making random adjustments in production.

### 12.6. Handling Ancestor Traversal

The Finance group has `r-x` on `acl-lab/finance` yet still needs `x` on the parent `acl-lab` and the filesystem root along the ACL path.

Logical requirement example:

~~~text
/ (root)           FINANCE: --x
/acl-lab           FINANCE: --x
/acl-lab/finance   FINANCE: r-x
file in finance    FINANCE: r--
~~~

**Do not set `other::--x` on root just to let Finance traverse** if policy requires only the Finance group to have access. Use named groups and check mask effects.

### 12.7. Readback After Setting ACLs

~~~bash
az storage fs access show \
  --account-name "$STORAGE" \
  --file-system "$FILESYSTEM" \
  --path "acl-lab/finance" \
  --auth-mode login \
  --output json
~~~

Reading back the configuration is necessary but **not sufficient**: test reading and attempting write/create operations with a real Finance identity, verifying they succeed or fail according to the matrix.

## 13. Recursive ACL Operations and Blast Radius

### 13.1. When Is Recursion Needed?

If the default ACL on `/curated/finance` was just updated, 5 million existing files **do not retroactively inherit it**, so an operator may need to update ACLs on older objects.

Common command families in admin tooling:

~~~bash
az storage fs access set-recursive --help
az storage fs access update-recursive --help
az storage fs access remove-recursive --help
~~~

**Do not run these commands** merely because they are named in this lesson; verify syntax, privileges, and scope first.

### 13.2. Difference Between `set` and `update`

- **Set-recursive** typically replaces entire ACLs along the path, risking removal of existing named entries.
- **Update-recursive** modifies/updates specified entries; verify exact API semantics.
- **Remove-recursive** removes specified entries, which can revoke access unexpectedly.

Recursive updates across large object counts can be **long-running operations**, encountering partial failures, 429/throttling, or interruptions. Nothing guarantees a single command applies atomically across millions of paths.

### 13.3. Recursive ACL Deployment Runbook

1. Identify the exact **filesystem/path prefix** and business owner.
2. Inventory total files/directories and sensitive data within the branch.
3. Export/save an ACL baseline using an authorized process.
4. Diff desired ACLs against current state, noting owners/ACEs that must be preserved.
5. Test on a **small subtree** containing no production data.
6. Choose the set/update/remove method with the exact required semantics.
7. Plan a maintenance window, retries, continuation/failure-list handling, and operation budgets.
8. Execute with a temporary privileged identity, capturing logs and approvals.
9. Read back ACLs on representative paths **and run functional tests**.
10. Reconcile failed batches, restoring the baseline if needed.
11. Ensure newly created directories still carry appropriate default ACLs.

### 13.4. Do Not Rewrite All ACLs When Only Parent Execute Is Missing

When a user has `r` on a file but hits 403 due to missing `x` on `/curated`, an approved fix to parent traversal may suffice; there is no need to run a recursive update over millions of files. Find the **smallest blocking point** to minimize blast radius.

### 13.5. Recursive Updates Do Not Override RBAC Roles

Even after updating every ACE in a filesystem, a principal can still access a "blocked" branch if granted **Storage Blob Data Contributor at the account scope** or holding a Shared Key. Fixing ACLs does not replace RBAC and key audits.

## 14. Azure Storage Data Lake SDK with Python

### 14.1. Why Use the SDK?

Use the SDK when:

- Building automated ACL audit/reconciliation tools.
- Inspecting path ownership, permissions, and default ACLs.
- Testing file creation and verifying inheritance.
- Integrating identity-based access into data processing.
- Orchestrating recursive ACL updates with error handling, retries, and partial-failure tracking.

**Never use an account key to test the ACL permissions of an Entra group.** Key-based auth is a separate access path and will yield misleading results.

### 14.2. Dependencies

In a **learner's local project**, without adding new files to the module:

~~~text
azure-storage-file-datalake
azure-identity
~~~

~~~bash
python -m pip install azure-storage-file-datalake azure-identity
~~~

Production environments should pin package versions and verify runtime compatibility.

### 14.3. Python: Reading ACLs with DefaultAzureCredential

~~~python
import os

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

account_name = os.environ["ADLS_ACCOUNT"]
file_system_name = os.environ.get("ADLS_FILESYSTEM", "lake")

service = DataLakeServiceClient(
    account_url=f"https://{account_name}.dfs.core.windows.net",
    credential=DefaultAzureCredential(),
)

fs = service.get_file_system_client(file_system_name)
directory = fs.get_directory_client("curated/finance")

acl = directory.get_access_control()

print("owner:", acl.get("owner"))
print("group:", acl.get("group"))
print("permissions:", acl.get("permissions"))
print("acl:", acl.get("acl"))
~~~

Prerequisites: HNS enabled on the account, Entra principal has permission to view ACL metadata, networking/TLS are valid, and SDK version is supported. On a laptop, `DefaultAzureCredential` may use the developer identity; on an Azure runtime, it uses a different managed/workload identity. Always verify the actual principal.

### 14.4. Reading a File by Path

~~~python
file_client = fs.get_file_client(
    "curated/finance/2026/invoices.parquet"
)

# Suitable only for small files in a lab.
contents = file_client.download_file().readall()
print("bytes received:", len(contents))
~~~

For large files, use streaming/chunks or a Spark Parquet reader. On a 403, check `x` on ancestors and `r` on the file, RBAC/ACLs, and identity; never switch to an account key to test.

### 14.5. Writing ACLs with the SDK (Illustrative Only)

~~~python
# WRITE OPERATION - DO NOT run on production:
# directory.set_access_control(
#     acl="user::rwx,group::r-x,other::---"
# )
~~~

`set_access_control` can drop existing named entries. In an application, use the SDK to **read and diff ACLs** against desired state before modifying; ACL management roles must be granted under audit.

### 14.6. Identity and Client Lifecycle

Instantiate `DataLakeServiceClient` appropriately and reuse the SDK's connection pooling across its lifecycle rather than creating a new client for every file in a large ETL job. Never log tokens, Shared Keys, user delegation SAS, or full signed URLs.

## 15. Authorization Matrix and Effective Access Testing

### 15.1. Team Goals

A file system:

~~~text
lake/
  landing/orders/
  curated/finance/
  curated/sales/
  analytics/daily/
  tmp/jobs/
~~~

| Path | Ingestion | ETL | Finance | BI | Auditor |
| --- | --- | --- | --- | --- | --- |
| `landing/orders` | Create/write | Read | No | No | No |
| `curated/finance` | No | Read/write | Read | No | Read in scope |
| `curated/sales` | No | Read/write | No | No | No |
| `analytics/daily` | No | Read/write | No | Read | Read in scope |
| `tmp/jobs` | No | Create/write/delete temp | No | No | No |

**"No" is a security goal**, not an ACL deny override. Achieving it requires no broad RBAC data roles, no unintended Shared Keys/SAS, and no unintended named ACLs.

### 15.2. Required Permissions on Ancestors

Example: Finance reading `/curated/finance/2026/report.parquet`:

~~~text
/                        Finance: --x
/curated                 Finance: --x
/curated/finance         Finance: r-x
/curated/finance/2026    Finance: r-x
/report.parquet          Finance: r--
~~~

In practice, the root path is the root of the **file system**; the filesystem name `lake` is not a child directory. These illustrative ACL entries must be translated into named group/user entries with **real object IDs**.

### 15.3. A Misconfigured Mask Strips Permissions

~~~text
group:<etl-group-id>:rwx
mask::r-x
~~~

Even though ETL has an `rwx` entry, the mask lacks `w`, so effective ACL permission denies writing. When updating a mask, ensure it does not unintentionally widen permissions for other named entries; inspect the entire ACL before editing.

### 15.4. Test Suite

| Test Case | Expected Result |
| --- | --- |
| Finance reads finance file by path | Succeeds |
| Finance lists finance directory | Succeeds if `r+x` is present |
| Finance creates file in finance | Denied |
| Finance accesses sales | Denied |
| BI reads analytics/daily | Succeeds |
| BI reads landing/orders | Denied |
| ETL creates file in curated/sales | Succeeds |
| ETL deletes file in granted write folder | Follows intended policy |
| Finance has valid ACL but network blocks | Still fails due to network |
| Finance unexpectedly holds account-wide Data Contributor | Negative tests may fail due to overly broad RBAC |
| Client uses account key instead of Entra identity | Does not prove Finance ACLs |

### 15.5. Testing Default ACLs with New and Old Files

1. Read the baseline ACL of directory `acl-lab/finance`.
2. Create `newdir` and `newfile` using an authorized ETL/owner identity.
3. Read the actual access/default ACL of `newdir` and access ACL of `newfile`.
4. Test Finance reading the new file.
5. Test Finance writing/deleting the new file; must be blocked if read-only.
6. Check a file created **before adding the default ACL** — its permissions do not change automatically.
7. Verify whether the default mask alters permissions from expectations.
8. Test with the **exact principal and credential**, not an administrator.

**Textual ACL readback is necessary but insufficient.** Effective access also depends on RBAC, tokens, Shared Key/SAS, networking, and the specific operation.


## 16. Applying HNS/ACLs in Azure Data Factory, Spark, and Analytics

### 16.1. Access from Data Processing Engines

An analytics solution typically includes:

~~~mermaid
flowchart LR
    SRC["Business systems"]
    ADF["Data Factory\nManaged identity"]
    LAND["ADLS Gen2\nlanding"]
    SPARK["Spark / Databricks\nWorkload identity"]
    CUR["ADLS Gen2\ncurated"]
    BI["BI / analytics\nRead-only identity"]
    REP["ADLS Gen2\nanalytics"]
    SRC --> ADF --> LAND
    LAND --> SPARK --> CUR
    CUR --> REP --> BI
~~~

These engines require storage access with the **proper identity and credential mode**. Never assume that because a pipeline uses Data Factory's managed identity, a Spark cluster automatically uses that same identity; each service has its own identity integration mechanism.

### 16.2. Mapping Operations to ACLs

| Operation | Path-Semantics ACL to Check |
| --- | --- |
| ADF writes new file to `landing/orders` | `x` ancestors, `w+x` parent |
| Spark reads Parquet file | `x` ancestors, `r` on file |
| Spark lists partition folders | `x` parents, `r+x` on directory to list |
| Spark creates output directory | `w+x` on parent along the path |
| Spark commits via rename/move | Permissions on source/destination parents per operation |
| BI reads aggregated data | `x` ancestors and `r` on files, `r+x` if listing folders |
| Pipeline deletes temporary files | `w+x` on directory holding entries, plus policies/constraints |

Some query engines need to **list partition directories** before opening files. Thus `--x` ACL may suffice for point-reading a known path, yet **be insufficient** for Spark discovery or BI browsing.

### 16.3. Rename and Inheritance

Suppose a data engineer creates a file in `/tmp/job-42` and then **moves** it to `/curated/finance`. **Do not assume a moved file inherits the destination directory's default ACL** as a newly created file there would; the ACL/ownership of an existing object may be preserved per rename semantics.

Proper runbook:

1. Identify how ETL outputs are created and committed (create vs. rename/move/copy).
2. Read the file's access ACL after commit.
3. Compare against the curated zone policy.
4. If needed, apply controlled ACL updates **after the move**, rather than assuming inheritance.
5. Test Finance read, ETL write, and denial for other groups.

This is a frequent cause of **newly pipeline-generated files** becoming unreadable even when the default ACL on `curated/finance` looks correct.

### 16.4. ACLs and Dataset Frameworks

In Parquet/Delta-style datasets, a "data table" typically consists of **multiple metadata and data files**. If an analyst has `r` on data files but lacks `r+x` on metadata directories, queries can still return 403. When creating datasets, apply policies to **both the dataset root directory and required child files**, testing with the actual query tool (Spark SQL, Power BI, Synapse, or the target engine).

Never assign `other::rwx` to metadata folders to fix a notebook error; the root cause is usually missing traverse, mask, ownership, or credential mode.

### 16.5. Separating Write Staging from Published Data

An operational pattern:

~~~text
/landing       ingestion writes
/tmp/jobs      ETL temporary write
/curated       ETL writes; business readers read
/analytics     BI reads, publish identity writes
~~~

Readers must not write to staging, and ETL must not receive account-wide `Storage Blob Data Owner` just to rename directories. In multi-team environments, a dedicated **publish pipeline identity** can handle moving data into controlled branches.

## 17. Network, TLS, Encryption, and Protecting Access Paths

### 17.1. Private Endpoints for Blob and DFS

An HNS-enabled Storage account can be accessed via:

~~~text
<account>.dfs.core.windows.net
<account>.blob.core.windows.net
~~~

When using **Azure Private Link**, design DNS and private endpoints around the endpoints clients actually use. Data Lake tools may hit both DFS/Blob endpoints or get redirected during certain operations. Configuring only one endpoint can result in timeouts or unexpected public routing.

Commonly involved Private DNS Zones:

~~~text
privatelink.dfs.core.windows.net
privatelink.blob.core.windows.net
~~~

**Verify the account's exact API/network model**, VNet links, on-premises DNS forwarding, and SDK mode. Never work around DNS issues by putting a raw private IP in the URL, as TLS validates the hostname.

### 17.2. Defense-in-Depth Structure

| Layer | Protects | Does Not Replace |
| --- | --- | --- |
| Firewall/Private Endpoint | Restricts sources and network paths | User identity and file permissions |
| TLS | Encrypts in transit and authenticates server | ACLs or RBAC |
| Entra ID/managed identity | Authenticates caller | Data permissions if not yet granted |
| Azure RBAC | Resource-scope data permissions | Fine-grained path ACLs when roles are too broad |
| Access/default ACL | Path-level permissions and inheritance | Not a deny override for Shared Key/Contributor |
| Account key policy/SAS | Limits credential types | Network security and data governance |
| Encryption at rest/CMK when supported | Protects stored data | Does not stop authorized deletions |
| Audit/alerts | Detection and investigation | Does not auto-fix permissions or restore files |

### 17.3. Checking DNS and TLS from the Right Machine

Linux/macOS:

~~~bash
STORAGE="stlakeunique001"
nslookup "$STORAGE.dfs.core.windows.net"
nslookup "$STORAGE.blob.core.windows.net"

nc -vz "$STORAGE.dfs.core.windows.net" 443
nc -vz "$STORAGE.blob.core.windows.net" 443
~~~

PowerShell:

~~~powershell
Resolve-DnsName stlakeunique001.dfs.core.windows.net
Resolve-DnsName stlakeunique001.blob.core.windows.net

Test-NetConnection stlakeunique001.dfs.core.windows.net -Port 443
Test-NetConnection stlakeunique001.blob.core.windows.net -Port 443
~~~

These commands only check DNS/TCP; **they do not prove access ACLs are right**. Nor should you infer from laptop results that a Spark cluster uses the same DNS or routing.

### 17.4. TLS and Public Access

Azure Storage endpoints use HTTPS/TLS. Never disable certificate validation when Private DNS is broken. Policies like **secure transfer required** can be configured on the account per supported options; test legacy accounts/clients before changing.

Even with valid TLS, a leaked Shared Key remains a risk. Conversely, a properly authorized managed identity cannot connect if public network access is blocked without a private route.

### 17.5. Encryption, CMK, and Data Residency

Azure Storage provides encryption at rest; certain accounts support **customer-managed keys** via Key Vault/managed identity subject to specific prerequisites. Using CMK requires designing key lifecycle, access rights, rotation, backup/restore, soft-delete, and procedures for key unavailability.

ACLs do not replace **encryption**, and encryption does not stop a user with data-plane permissions from deleting files. For financial/PII data, evaluate storage account boundaries, region, retention, network restrictions, and auditing per policy.

### 17.6. Security for Key-Using Tools

Never place account keys or long-lived SAS tokens in public notebooks, build logs, or browser clients. Prefer managed identity + Entra data permissions wherever SDKs/workloads support them. When SAS is required, limit expiry, resource scope, and operations, and guard the URL as a secret.

## 18. Observability, Auditing, and Permission Drift

### 18.1. Why an ACL Snapshot Alone Is Not Enough

ACLs on `/curated/finance` may be right today, yet tomorrow:

- An IaC deployment grants account-wide Data Contributor to a reporting group.
- An ETL move creates files that do not inherit the intended ACL.
- A member is added to the wrong group.
- A recursive operation unexpectedly changes the mask.
- A notebook starts using an account key.
- Private Endpoint/DNS changes route clients over a different network path.
- An auditor gains rights on another container outside business scope.

Therefore, **periodic effective-access tests and RBAC/ACL audits** are required, not just an initial permissions snapshot.

### 18.2. Signal Sources

| Source | Monitors |
| --- | --- |
| Azure Activity Log | Resource changes, Azure role assignments, network settings |
| Azure Storage diagnostic settings | Supported operation logs, 401/403s, request IDs, latency |
| Storage metrics | Transactions, ingress/egress, availability, latency, and error patterns |
| Application/pipeline logs | Dataset path, job ID, principal, operation, result |
| Entra audit | Group/role membership and identity lifecycle |
| IaC drift checks | Resource/permission settings diverging from desired state |
| Security alerts | Shared Key usage, anomalous access, privilege changes per capabilities |
| FinOps | Operations/storage/retention/replication costs |

**Do not assume Storage diagnostic logs capture every ACL ACE or file content.** Auditing ACL changes requires combining service-supported activity/data-plane events, change-management logs, and authorized ACL snapshots.

### 18.3. Metric Definitions via Azure CLI

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query id --output tsv)

az monitor metrics list-definitions \
  --resource "$STORAGE_ID" \
  --output table
~~~

Metric names and dimensions can vary by resource, provider, and region. Use the actual account's definitions rather than copying a metric name from a non-HNS account and assuming it exists.

### 18.4. Sample Log on Access Denial

~~~json
{
  "timeUtc": "2026-11-20T12:00:00Z",
  "pipeline": "finance-curation",
  "path": "lake/curated/finance/2026/report.parquet",
  "operation": "ReadFile",
  "authMode": "MicrosoftEntra",
  "principalId": "<object-id>",
  "result": "AuthorizationPermissionMismatch",
  "correlationId": "job-42"
}
~~~

This is an **illustrative pipeline-defined log schema**, not a guarantee that Azure emits these exact fields. In production, avoid logging PII, account keys, SAS URLs, or file contents.

### 18.5. Useful Alerts

- Spike in 403/authorization failures after deployment.
- Sudden surge of data DELETE/rename operations or recursive ACL changes.
- New account-scope RBAC Data Owner/Contributor outside change windows.
- Storage account Shared Key policy unexpectedly re-enabled.
- Public network access/firewall widened without approval.
- Finance analyst unexpectedly succeeds in reading a sales path during an access test.
- Transaction/data processing volume spikes disproportionate to business workload.
- Diagnostic logs disabled or missing data.
- Operations cost jump during bulk ACL remediation.

Every alert needs an owner, severity, threshold, and runbook. A spike in 403s may result from a legitimate negative access test; review context before escalating severity.

## 19. Playbook: Handling 403s, Missing ACLs, and Misconfigured Permissions

### 19.1. Common Symptoms

| Symptom | Likely Cause | Evidence to Gather |
| --- | --- | --- |
| `AuthorizationPermissionMismatch` | Missing role data action or ACL permission/mask | RBAC, path ACL, ancestors |
| `AuthorizationFailure` or network 403 | Firewall/VNet rules/credential | Network configuration and request error |
| Wrong DNS endpoint | Private DNS/forwarding | DNS resolution from actual client |
| TCP 443 timeout | NSG/UDR/firewall/Private Endpoint | Routing and connectivity |
| CLI succeeds, Spark job gets 403 | Different principal or credential mode | Entra object ID, account key/SAS, workload identity |
| File read fails despite `r--` file ACL | Ancestor missing `x` | Root/parent access ACLs |
| Named group has `rwx` but cannot write | `mask::r-x` or missing parent permissions | Effective ACE, parent `w+x` |
| Added default ACL but old files still 403 | Default ACL is not retroactive | Creation time and current access ACL |
| Finance can also read sales | Inherited Data Reader/Contributor role or Shared Key | Role assignments/credentials |
| Spark rename to curated breaks Finance read | Moved path kept unexpected ACL | ACL after rename and publish workflow |
| List directory fails while point-read works | Directory lacks `r` but has `x` | Operation-specific ACL |
| Data Lake SDK works over DFS, Blob tool fails | Private endpoints/DNS or API compatibility | DFS + Blob network paths |
| Recursive ACL finishes with failed files | Partial failures, throttling, continuation | Operation logs/failure list |
| 404 path not found | Wrong filesystem/path/casing or already moved | Path existence, namespace |
| User recently added to group still gets 403 | Token/cache/propagation delay, wrong object ID | Group membership and identity token |
| Data deleted after granting write on parent | Parent `w+x` grants entry deletion | Parent ACL and data-plane RBAC |

### 19.2. Step 1 — Verify Environment and Identity

Record the Azure subscription, tenant, account, filesystem, path, and principal object ID. **Do not print secrets.** Check whether the client uses Entra OAuth, an account key, or SAS, since ACL evaluation differs by credential type.

### 19.3. Step 2 — Separate Networking from Data Permissions

If DNS/TCP/TLS fails, fix networking first. If you receive 401, inspect authentication and tokens/credentials. If 403, capture **HTTP error code, storage substatus, x-ms-request-id** (if present), and the specific operation to distinguish network ACLs from path authorization.

Never fix a 403 with `other::rwx`, an account key, or account-wide Data Owner before identifying the root cause.

### 19.4. Step 3 — Analyze ACLs Segment by Segment

For `/curated/finance/2026/report.parquet`:

~~~text
root            : x
curated         : x
finance         : x
2026            : x
report.parquet  : r
~~~

To list `2026`, `r+x` is required on that directory. To create/delete under `2026`, `w+x` on the parent is typically needed. Check the mask and effective group permissions.

### 19.5. Step 4 — Analyze RBAC and Bypass Paths

Check inherited roles at subscription/resource group/account scopes, roles at container scope, group memberships, and permissions to retrieve storage account keys. If a user holds account-wide Data Contributor, editing ACLs will not revoke that broad permission; **adjust the role assignment/credential** via security review.

### 19.6. Step 5 — Correlate with Recent Changes

- Was the file newly created or moved from staging?
- Did the default ACL exist when the object was created?
- Did a recursive ACL job run?
- Did the pipeline recently switch managed identity/service principal?
- Did group membership or ownership change?
- Were networking/Private DNS modified?
- Was an old account key/SAS rotated or a policy disabled?

Document the timeline and evaluate rollback options before running remediation.

### 19.7. Step 6 — Apply Minimal Fix and Retest

Change only the required path/ACE/mask or RBAC scope; run positive and negative tests using the real identity. Read back ACLs, monitor 403 rates/latency, and verify no unintended permissions were introduced. For large changes, ensure approver sign-off and a rollback plan.


## 20. Change Management, Cost, and Permission Auditing

### 20.1. Production Authorization Workflow

A request to "let the Finance team read revenue reports" should follow this workflow:

1. Business/data owner approves the **use case** and dataset.
2. Security validates personal data, retention, region, and legal scope.
3. Platform team identifies the identity/group object ID, RBAC scope, and credential mode.
4. Data engineer determines the filesystem/path, directory hierarchy, and actual operations (list/read/write/rename).
5. Design access ACL, default ACL, mask, and ancestor traversal.
6. Audit existing inherited RBAC roles, group memberships, and Shared Key/SAS usage.
7. Test in staging with **positive and negative access tests**.
8. Review IaC/config changes, obtain approval, and deploy within a maintenance window if needed.
9. Read back ACL/RBAC and verify with the actual consumer/application.
10. Record the owner, ticket, expiry/review date, evidence, and rollback instructions.

**Never submit a single ACL screenshot and mark the audit PASS.** Tests must demonstrate both that intended access works and that unintended access is denied.

### 20.2. Permission Drift

Changes prone to causing drift:

- A departing user remains in a named ACE.
- A group changes ownership or receives members outside process.
- A new ETL job creates files with a different owner/default ACL.
- A recursive ACL job alters masks or `other` permissions.
- RBAC Contributor is assigned at a parent scope.
- An account key is shared or Shared Key access is re-enabled.
- A new container is created with ACLs diverging from policy.
- Data is exported to an account lacking equivalent security controls.

Maintain a **desired-state ACL matrix**, periodically read actual RBAC/ACLs to compare, and avoid auto-remediating without approval when there is risk of breaking legitimate access.

### 20.3. Versioning ACL Policies

Example desired-state metadata in an IaC/policy repository (illustrative, **not a file created in the module**):

~~~yaml
dataset: finance-orders
filesystem: lake
path: curated/finance
ownerTeam: finance-platform
environment: production
allowed:
  finance-readers:
    directory: r-x
    file: r--
  finance-publisher:
    directory: rwx
    file: rw-
defaults:
  inheritReadForNewFiles: true
denyOtherByDefault: true
reviewCadence: quarterly
~~~

This is a **team policy specification**, not ARM/Bicep/Terraform/ACL syntax ready for Azure CLI. When translating into Azure ACEs, include owner/group/mask/other, Entra object IDs, and ancestor traversal, while also checking RBAC/key paths. Naming a flag `denyOtherByDefault` only expresses the goal of granting `other` no access, not that Azure POSIX ACLs have an explicit deny entry.

### 20.4. Cost Model

| Cost Source | Driver |
| --- | --- |
| Stored data | Capacity, replication, tier, and region |
| File/path operations | Directory create/list/rename, reads/writes |
| Recursive ACL updates | Scanning and updating large path counts |
| ETL compute | Data Factory, Spark, Databricks, Synapse workloads |
| Logging/Monitoring | Diagnostic logs, Log Analytics ingestion/retention |
| Networking | Private Endpoints, egress, hybrid connectivity |
| Backup/retention | Soft delete, versioning, supported retention features |
| Data duplication | Copies to staging/curated/other accounts |
| Security operations | Key Vault/CMK and governance automation |

**Do not apply fixed price assumptions across every region/SKU.** HNS-enabled accounts, file counts, and operation patterns affect costs. Use the Azure Pricing Calculator and Cost Management for your actual account, tier, and region.

### 20.5. Avoiding Small-File Explosion

A pipeline producing 10 million 1 KiB files triggers heavy metadata operations during listing, renaming, and ACL updates, even though total raw payload is only around 10 GiB.

For data analytics:

- Compact small files into Parquet files sized appropriately for the workload.
- Organize partitions around real queries, avoiding unnecessary directories.
- Run controlled file compaction and ensure ACLs on compacted files match policy.
- Avoid frequent recursive ACL updates when policies can be set properly **before data creation** via default ACLs.
- Attach cost budgets to automation and watch for activity spikes.

### 20.6. Rollback After a Bad ACL Change

If a deployment grants wrong permissions:

1. Isolate unintended access if there is data exposure risk.
2. Collect pre-change evidence (ACL/RBAC snapshots and approvals).
3. Revoke overly broad roles/data permissions or fix the exact ACE/parent mask.
4. For recursive changes, remediate in batches using failure lists and the baseline.
5. Run negative tests with the affected principal.
6. Verify legitimate pipelines continue operating.
7. Assess whether data was read/written/deleted improperly, rather than looking solely at current permissions.
8. Write a postmortem and strengthen guardrails.

**ACL rollback does not restore deleted files.** Data recovery is a separate process relying on configured and supported soft delete, versioning, backup, and recovery features.

## 21. Capstone Practice: Building an Authorization Model

### 21.1. Problem Statement

A company uses ADLS Gen2 for e-commerce data:

~~~text
Storage account: stlakeunique001
HNS: enabled
File system: lake

Paths:
  landing/orders/2026/11/
  curated/finance/2026/
  curated/sales/2026/
  analytics/daily/
~~~

Requirements:

- `mi-ingestion` may only ingest raw data into `landing/orders`.
- `grp-engineers` reads raw and outputs clean data to `curated`.
- `grp-finance` lists and reads `curated/finance`, cannot write/delete, and cannot view `sales`.
- `grp-bi` reads only `analytics`.
- `grp-acl-admin` administers ACLs per ticket.
- Production data must not be accessed via widely distributed account keys.
- Access must pass through appropriate networking policies, auditing, and cost budgets.

### 21.2. Exercise A — Designing the ACL Tree

**Prompt:** list the minimum permissions for `grp-finance` to read `/curated/finance/2026/orders.parquet` and list the `2026` folder.

**Answer:**

~~~text
/                         --x
/curated                  --x
/curated/finance          r-x
/curated/finance/2026     r-x
/orders.parquet           r--
~~~

These symbols represent the **permissions of the named Finance group** at each corresponding path, not complete ACL strings. You must still account for masks, owner/group/other, and RBAC effective access. For new files to be readable under policy, configure appropriate default ACLs on directories where files will be created.

### 21.3. Exercise B — Why Does `r--` on a File Still Return 403?

Finance has access ACE `user:FIN:r--` on the file, but `/curated` does not grant traverse `x`.

**Answer:** missing `x` on an ancestor prevents reaching the file via ACLs. Add the required traversal permission on the authorized parent rather than granting account-wide data owner.

### 21.4. Exercise C — Why Can a Named Group with `rwx` Not Write?

Directory ACL:

~~~text
user::rwx
group::r-x
group:<etl-group-id>:rwx
mask::r-x
other::---
~~~

**Answer:** the mask strips `w` from the named group, leaving effective `r-x`. Inspect the mask and all named entries before making changes.

### 21.5. Exercise D — Do Default ACLs Affect Old Files?

`/curated/finance` received a default ACL for Finance after `old.csv` already existed. Users still cannot read `old.csv`.

**Answer:** default ACLs do not alter ACLs on existing objects. Inspect the current access ACL on the file and run a controlled update; never run recursive `set` across an entire production container.

### 21.6. Exercise E — ACL Denies Access Yet User Reads Sales

Finance has `other::---` on Sales, yet holds `Storage Blob Data Reader` across the entire storage account.

**Answer:** an RBAC data role can grant read access despite restrictive ACLs. Narrow the RBAC role/scope or separate containers/accounts, then run negative tests.

### 21.7. Exercise F — Pipeline Uses Account Key

An ETL job uses a Shared Key and can read the entire account; the ETL group does not yet have proper ACLs.

**Answer:** this **is not proof that ETL ACLs work**. Switch the lab job to an Entra identity, verify ACLs/RBAC, and retire the key per the security plan.

### 21.8. Exercise G — Rename Causes BI to Lose Read Access

A pipeline writes files to `/tmp` and moves them to `/analytics`. BI gets 403 even though the default ACL on `analytics` grants read access.

**Answer:** the file was **moved**, not newly created under the destination parent, so it does not automatically inherit the destination default ACL. Inspect ACLs after rename and adjust the publish workflow accordingly.

### 21.9. Exercise H — Folder Has `r--`, Missing `x`

BI knows the exact file path, yet parent `/analytics` has `r--` on the directory.

**Answer:** missing traverse `x`. `r` on a directory permits listing, not replacing `x` to reach children. Grant `r-x` if BI needs both listing and traversal, or `--x` if only known-path access is required.

### 21.10. Exercise I — `set` Used Instead of `update`

An operator runs `az storage fs access set` with only the three base entries on `curated/finance`, wiping out named ACEs.

**Answer:** `set` can replace the existing ACL. Restore the full baseline/ACEs per runbook, use supported `update` APIs where appropriate, and test on a small subtree first.

### 21.11. Exercise J — Private Endpoint Only for DFS

Spark reads over DFS work, while a Blob API tool times out inside a private-only network.

**Answer:** check Private Endpoint/DNS/routing for `blob.core.windows.net` in addition to `dfs.core.windows.net`; never disable TLS or open wide Internet access as a workaround.

### 21.12. Exercise K — Recursive ACLs and Cost

A job runs a recursive ACL update across 8 million files just to grant `x` on one ancestor.

**Answer:** halt and reconsider; fixing permissions on the ancestor and relevant paths alone may suffice. Recursive operations drive up cost, partial-failure risk, and blast radius.

### 21.13. Exercise L — Evaluating Write/Delete When Parent Has `w+x`

A user has `w+x` on the folder containing a file, but lacks `w` on the file itself.

**Question:** can they delete the file?

**Answer:** in the directory permissions model, deleting an entry typically relies on `w+x` on the parent (alongside other constraints), not just `w` on the file. Test the exact operation and protect parent directory ACLs accordingly.

## 22. Self-Check Questions

**Question 1.** What does Hierarchical Namespace mean?

**Answer:** HNS turns directories into real entities in Blob Storage's namespace, supporting directory/file-system-oriented operations and path-level ACLs on ADLS Gen2.

**Question 2.** What does a file system in ADLS Gen2 correspond to?

**Answer:** A Blob container in an HNS-enabled storage account.

**Question 3.** How does the DFS endpoint differ from the Blob endpoint?

**Answer:** DFS serves filesystem/path and ACL operations; the Blob endpoint serves supported Blob APIs. Both point to the same storage account data, though workflows and Private Endpoints may require both.

**Question 4.** How do Access ACLs and Default ACLs differ?

**Answer:** Access ACLs govern existing objects; default ACLs on directories act as inheritance templates for newly created objects without retroactively modifying existing data.

**Question 5.** Why can a file with `r--` still return 403?

**Answer:** A parent directory may lack `x`, or another authorization requirement may be unmet; also check RBAC, networking, and credentials.

**Question 6.** What is `r-x` on a directory used for?

**Answer:** Listing and traversing the directory, without creating or deleting entries as `w+x` allows.

**Question 7.** Does the mask affect a named user with `rwx`?

**Answer:** Yes. For example, `mask::r-x` strips `w`, preventing the effective ACL from writing.

**Question 8.** Will an `other::---` ACL block a user who already has account-wide Storage Blob Data Contributor from writing?

**Answer:** Do not assume so. Broad data-plane RBAC can authorize the operation independently of restrictive ACLs.

**Question 9.** Does the Azure Reader management role automatically allow reading files in ADLS?

**Answer:** Not directly; data access requires an RBAC data role, ACL, or another supported credential.

**Question 10.** Is a control-plane Contributor completely unable to access data?

**Answer:** You cannot conclude that: permission to retrieve storage account keys combined with Shared Key policy can create an indirect data access path.

**Question 11.** When should you use an Entra group to assign ACLs?

**Answer:** When multiple users require the same functional permissions, paired with clear membership governance and auditing.

**Question 12.** Why not use a Shared Key to prove Finance ACLs?

**Answer:** Key-based authorization differs from Entra/ACL, granting broad access and bypassing the ACL scope you intend to test.

**Question 13.** Why doesn't a destination directory's default ACL automatically apply to a moved file?

**Answer:** The file is an existing object; rename/move does not by default count as creating a new object under default ACL rules. Inspect ACLs after the operation.

**Question 14.** What risks does `set-recursive` carry?

**Answer:** It can overwrite many ACLs, drop critical ACEs, cause 403 outages or privilege escalation, suffer partial failures, and incur high operation costs.

**Question 15.** Is having a finance path and a group named `Finance` enough to set an ACL?

**Answer:** No. You need the verified Entra group object ID, ancestor permissions, and mask; display names are not safe principal IDs.

**Question 16.** Is `--x` on a directory enough to list file names?

**Answer:** No. It permits traversal for a known path, whereas listing typically requires `r+x`.

**Question 17.** Does a Private Endpoint for DFS guarantee all Blob API calls are private?

**Answer:** Not by default. Inspect the client's actual paths and configure a Private Endpoint/DNS for the Blob endpoint if the workload uses it.

**Question 18.** Is updating ACLs across millions of objects an atomic transaction?

**Answer:** Never assume so. Recursive operations can be long-running, experience partial failures, and require retries, continuation, and verification.

**Question 19.** Does `other::---` guarantee absolutely that a user cannot access data?

**Answer:** No. RBAC data roles, owner/named ACEs, account keys/SAS, and credential types must all be evaluated.

**Question 20.** If a principal has `w+x` on a parent directory but lacks `w` on a file, what is noteworthy?

**Answer:** They may be able to delete/rename the entry in the directory per operation semantics despite lacking permission to modify file contents; protect parent ACLs.

**Question 21.** What should be verified after granting Finance read permissions?

**Answer:** Reading target files succeeds, listing allowed folders succeeds, writing/deleting fails, and reading Sales fails—all tested with the real identity and auth mode.

**Question 22.** When should you separate containers or storage accounts instead of relying solely on directory ACLs?

**Answer:** When strong isolation, independent policies/lifecycles/networking, or resource-scope RBAC are required as the more suitable control.

## Key Takeaways

- **ADLS Gen2 = Azure Blob Storage with Hierarchical Namespace (HNS)**, supporting real directories, file-system operations, and path-level ACLs.
- **Access ACLs** govern existing objects; **default ACLs** pass templates to new children per service rules without updating old files.
- On directories, **`x` = traverse**, `r+x` permits listing/entering, and `w+x` can permit creating/deleting entries; always consider parent permissions.
- **The ACL mask can reduce effective permissions** of the owning group and named users/groups even when entries show `rwx`.
- **Azure RBAC data permissions and ACLs are not two mandatory deny layers.** Overly broad Reader/Contributor roles or Shared Keys can defeat intended ACL restrictions.
- **Managed identity + Entra groups + least privilege** reduce key dependency; test with the real principal, not an admin account.
- **DFS/Blob Private Endpoints, DNS, TLS, RBAC, and ACLs** are complementary layers of defense, not substitutes for one another.
- **Recursive ACL changes and data moves** must be reviewed, tested, and read back; rename/move should not be assumed to inherit destination default ACLs.
- A production data lake requires an **RBAC/ACL inventory, negative access tests, auditing, permission drift monitoring, a rollback plan, cost budgets, and dataset owners**.

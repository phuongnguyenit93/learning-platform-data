# Containers, Blobs, and How Object Data Is Organized

A modern application often needs to store product images, PDF documents, CSV files, videos, report exports, or event logs. This data is not necessarily suited for direct storage in relational database columns. **Azure Blob Storage** is an object storage service that stores and retrieves large volumes of file-based or unstructured data through Azure-managed APIs.

This lesson belongs to the **Object Storage with Blob Storage** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, while teaching how to deploy, monitor, secure, and control costs for an application architecture. The focus of this lesson is understanding **storage accounts, containers, blobs, and object naming/organization**, then applying security, lifecycle management, and hands-on operations.

After this lesson, you will be able to:

- Distinguish between a **storage account**, a **container**, a **blob**, and a blob name.
- Describe a blob URL and distinguish object storage from traditional file systems.
- Understand **block blobs**, **append blobs**, **page blobs**, and their primary use cases.
- Design container and blob names using scalable conventions that are easy to list by prefix.
- Distinguish flat namespace **virtual directories** from Data Lake Storage **hierarchical namespace**.
- Use **metadata**, **blob index tags**, versioning, and access tiers for their intended purposes.
- Design data protection using Entra ID/RBAC, private containers, encryption, versioning, and soft delete.
- Create containers, upload, list, download, and clean up test resources using Azure CLI.

## 1. What Problem Does Object Storage Solve?

In object storage, each object consists of **data content**, an **identifier/name**, and associated attributes. Applications access objects via APIs instead of interacting directly with a disk attached to a server.

For example, an e-commerce site might store:

- Product images: millions of JPEG/PNG/WebP images.
- Invoice PDF files: each invoice is a blob.
- Report export CSV files: generated on demand with a retention period.
- Tutorial videos: distributed through the application and CDN/edge systems when needed.
- Raw analytics data: JSON, CSV, or Parquet files partitioned by date.

In the database, the application typically only needs to store business information such as **DocumentId**, **OwnerId**, **BlobName**, **ContentType**, status, and access permissions. The file content resides in Blob Storage. This design allows file lifecycles and transactional data lifecycles to be managed according to the characteristics of each data type.

### How Does Object Storage Differ from File Storage and Databases?

| Criterion | Blob object storage | File share | Database |
|---|---|---|---|
| Typical unit of operation | Named object/blob | Files and directories in a file system | Records, tables, or data documents |
| Common access | HTTPS REST/SDK, Azure tools | SMB/NFS depending on the service | SQL/drivers/data APIs |
| Optimized for | Files, images, logs, raw data, object backups | Applications requiring file sharing via file system protocols | Queries, transactions, and data constraints |
| Data lookup | Listing by name/prefix, properties, tags when supported | Directory traversal | Indexes and business queries |
| Updates | Typically read/written via appropriate APIs | Read/write via file system operations | Transactional record modifications |

Blob Storage does not replace a database for arbitrary business data search or analysis. When querying by customer, order status, or per-document authorization is needed, applications typically maintain a **business catalog/index** in a database or appropriate search service.

## 2. Hierarchy Model: Storage Account → Container → Blob

Azure Blob Storage organizes objects into the following components:

~~~text
Azure subscription
└── Resource group: rg-shop-prod
    └── Storage account: stshopassetsprod
        └── Blob service
            ├── Container: product-images
            │   ├── products/p001/main.webp
            │   └── products/p002/main.webp
            ├── Container: invoices
            │   ├── 2026/11/inv-0001.pdf
            │   └── 2026/11/inv-0002.pdf
            └── Container: exports
                └── reports/2026/11/summary.csv
~~~

**Storage account** is an Azure resource with a globally unique name within the service namespace. It provides endpoints, deployment region, redundancy configuration, network access, and various account-level security/storage options.

**Container** is a unit for grouping blobs within the same storage account. A container has a unique name within the account, serves as a management boundary, and can act as a scope for data permissions or public access settings (if permitted by the account and policies). A container is not a virtual machine or a Docker container.

**Blob** is a data object stored in a container, having a name, content, and properties. Each blob is identified by the combination of **storage account + container + blob name**. The same blob name can appear in two different containers without conflict.

### URL of a Blob

With the default Blob endpoint, the URL pattern is:

~~~text
https://<storage-account>.blob.core.windows.net/<container>/<blob-name>
~~~

Example:

~~~text
https://stshopassetsprod.blob.core.windows.net/product-images/products/p001/main.webp
~~~

This is an example of URL structure, not an assertion that the blob is public or that the resource exists. **Knowing the URL does not mean having read permission**: private containers require a valid authorization method. Special characters in blob names must be URL-encoded according to HTTP rules.

A storage account can also have a custom domain, private endpoint, or other service endpoints depending on configuration. Do not attempt to infer the actual access domain solely from the container name.

## 3. Storage Account and Container: Choosing Organizational Boundaries

Before naming individual blobs, define the **management boundaries**:

| Question | When to consider separate storage accounts | When one account with multiple containers is usually suitable |
|---|---|---|
| Security/network | Workloads require very different network/identity/key policies | Same access and compliance model |
| Region and redundancy | Data must reside in a different region or replication configuration | Same region and similar storage requirements |
| Governance and cost | Need clear separation of responsibility, subscriptions, or monitoring quotas | Shared operations team and budget |
| Data lifecycle | Data groups have different account-level requirements | Controllable via containers, prefixes, and lifecycle rules |
| Scalability | Need independence in capacity, service limits, or administration | Current account scale and limits are sufficient |

**Containers** are suitable for grouping data by business domain, protection level, or lifecycle, for example:

- **product-images**: images processed and distributed through the application.
- **invoices-private**: private invoices with long retention and strict permissions.
- **raw-ingestion**: newly received files from source systems awaiting validation.
- **processed-data**: validated data usable for analytics.
- **temporary-exports**: temporary export files with a cleanup schedule.

Do not create a new container for **each file** without an administrative reason; doing so complicates access permissions, automation, and lifecycles. Conversely, putting all data into a single container can make authorization, retention management, and monitoring difficult.

A generally good decision is to group by **data purpose and policy**, then use blob names/prefixes to organize by tenant, data type, and time.

## 4. Naming Rules for Storage Accounts, Containers, and Blobs

### Storage account name

The storage account name used for endpoints must:

- Be **3–24 characters** long.
- Consist only of **lowercase letters a–z and numbers 0–9**.
- Be globally unique within the Azure storage account namespace.

Format-valid example: **stshopassetsprod01**. This name may still already be taken by someone else; you must verify availability upon creation.

### Container name

Container names generally follow DNS rules:

- **3–63 characters** long.
- Use lowercase letters, numbers, and hyphens (**-**).
- Start and end with a letter or number; no consecutive hyphens.

Examples: **product-images**, **invoices-private**, **raw-ingestion**. Do not use spaces, uppercase letters, or underscores in container names.

### Blob name

Blob names are more flexible: they can contain **/** to represent logical paths, for example:

~~~text
tenants/t001/orders/2026/11/20/order-000001.json
~~~

Some practical principles:

1. Use structured, consistent names that do not contain sensitive data.
2. Choose **one casing style** (usually lowercase) and a consistent delimiter convention.
3. Blob names are **case-sensitive**; **Report.pdf** and **report.pdf** are two different names.
4. Use stable identifiers (UUIDs/business IDs) rather than relying solely on user-submitted filenames.
5. Define a clear overwrite policy: uploading to the same blob name will replace content or create a new version if versioning is enabled appropriately.
6. Do not assume renaming a blob in a flat namespace is as cheap and atomic as renaming a file in a file system.
7. Check name, character, and path segment limits for the account type and namespace mode in use.

Names containing multiple **/** characters can be convenient for humans, but they do not always create real directories. This is explained in the next section.

## 5. Virtual Folders and Prefixes in a Flat Namespace

In Blob Storage's **flat namespace**, names like:

~~~text
orders/2026/11/20/0001.json
orders/2026/11/20/0002.json
orders/2026/11/21/0003.json
customers/c001/avatar.webp
~~~

are typically **full blob names**, not a physical directory structure like NTFS/ext4. The **/** character is simply part of the blob name; Azure Portal and Storage Explorer can display the parts before slashes as **virtual directories** for easier browsing.

For example, the Blob service can provide listing by prefix:

~~~text
Prefix: orders/2026/11/20/
Result:
  orders/2026/11/20/0001.json
  orders/2026/11/20/0002.json
~~~

This helps applications retrieve objects by period or source group. However, **prefixes are not a default security boundary**. Someone granted read permission on the entire container is not restricted just because the application uses the prefix **customers/c001/**. To enforce directory/object-level permissions, you must use an appropriate mechanism supported by the service or separate containers/accounts and enforce authorization in the application.

### Listing by Prefix Is Not Equivalent to SQL Queries

Blob names can be listed by name and prefix. However:

- Prefixes are useful if the application knows the exact leading portion of the key.
- This does not make Blob Storage a full-text search engine for file contents.
- You should not download a list of all blobs and filter client-side when data grows very large.
- When results are large, the SDK/REST API may return paginated responses; you must handle the **continuation token** until iteration finishes.
- Business queries such as "all images belonging to approved products that have not expired" usually require a separate catalog or index.

### When Should You Use Hierarchical Namespace?

**Azure Data Lake Storage Gen2** adds **hierarchical namespace (HNS)** capability to eligible storage accounts. When enabled, files and directories are represented with hierarchical semantics, supporting more efficient directory management operations and path-level permission mechanisms such as ACLs based on service capabilities.

| Characteristic | Flat Blob namespace | Hierarchical namespace (Data Lake Storage Gen2) |
|---|---|---|
| Directories | Primarily prefixes/virtual directories | Directories with hierarchical semantics |
| Renaming/moving paths | Often requires copying then deleting objects in many scenarios | Supports atomic directory rename/move via appropriate APIs |
| Path-based permissions | No built-in directory ACLs by default | Supports ACL and RBAC models by design |
| Typical use cases | Images, application files, backups, and media | Analytics lakes, data pipelines needing directory operations |

**HNS is a storage-account-level architectural decision**, requiring evaluation of feature compatibility, security, cost, tooling, and migration paths before enabling. Just seeing **/** in a blob name does not mean the account is using Data Lake Storage Gen2.

## 6. Three Blob Types: Block, Append, and Page

Azure Blob Storage supports three main blob types with different write behaviors:

| Type | How it works | When it fits |
|---|---|---|
| **Block blob** | Content consists of blocks; optimized for uploading and storing file/object data | Images, documents, videos, exports, analytics data |
| **Append blob** | Supports adding data to the end using an append model | Certain specialized log/append-only workloads |
| **Page blob** | Stores pages with random update capabilities in supported units | Workloads requiring random read/write, such as certain VHD scenarios |

**Block blobs** are the most common choice for application data. SDKs can split large files into blocks and commit the block list; applications do not need to implement this protocol manually when using an appropriate SDK.

**Append blobs** provide append-to-end semantics, but do not automatically create a distributed logging system with global ordering, indexing, or smart retention. For application logs that require searching/querying, also evaluate Azure Monitor/Log Analytics, Event Hubs, or an appropriate log processing service.

**Page blobs** target a different access pattern than block blobs. Do not choose page blobs merely because data is large; base your choice on I/O patterns and account tier/support limits.

## 7. Organizing Data by Domain, Tenant, and Time

Good naming design makes storage easier to manage and process, but you should not turn blob names into a repository for all business data.

### Option A: E-commerce application

~~~text
product-images/
  products/p001/v3/main.webp
  products/p001/v3/thumb.webp
  products/p002/v1/main.webp

invoices-private/
  year=2026/month=11/invoice-000001.pdf
  year=2026/month=11/invoice-000002.pdf

temporary-exports/
  job-8e2f/report.csv
  job-9c1b/report.csv
~~~

In this example, the lines beneath the container names are **blob names**. Grouping by product and version helps prevent unintended overwrites. Grouping by time makes it easier for applications to browse and reconcile, especially with high-volume data.

### Option B: Multi-tenant SaaS

~~~text
Container: uploads-private
  tenants/t001/documents/2026/11/doc-9a81.pdf
  tenants/t002/documents/2026/11/doc-4b26.pdf

Container: processed-private
  tenants/t001/results/job-101.json
  tenants/t002/results/job-205.json
~~~

**Important warning:** Putting **tenants/t001/** and **tenants/t002/** in blob names **does not isolate access permissions per customer**. The backend must:

1. Authenticate the caller's token/session.
2. Determine the tenant/customer from the authenticated identity.
3. Check read, write, or delete permissions **per object** according to business policy.
4. Map the customer to the correct container/prefix server-side.
5. Only issue URLs or minimally scoped SAS tokens after authorization.

If strong isolation is required, consider **separate containers**, **separate storage accounts**, separate network/security boundaries, or HNS ACLs as supported by the service. Never rely solely on a customer ID string submitted by the client in the request.

### Option C: Date-partitioned analytics data

~~~text
Container: events-raw
  source=web/year=2026/month=11/day=20/part-0001.json
  source=web/year=2026/month=11/day=20/part-0002.json
  source=mobile/year=2026/month=11/day=20/part-0001.json
~~~

The **key=value** path style is often useful for analytics tools when the pipeline is designed to recognize partitions. However, having **year=2026** in the name does not automatically create database partitions or query indexes; that capability depends on the data-reading engine.

### Choosing Prefix Order

If an application frequently queries "all files for tenant t001 on day 20", a pattern like **tenants/t001/events/2026/11/20/** enables listing with a full prefix. If it frequently performs daily aggregations across all tenants, consider a different layout or maintain a manifest/index to avoid scanning too many prefixes.

Do not optimize solely for readability. Base your design on **access patterns, volume, lifecycle, authorization, and processing workflows**.

## 8. Metadata, HTTP Properties, and Blob Index Tags

Beyond content, a blob can carry different descriptive information. Three groups are commonly confused:

| Component | Purpose | Examples |
|---|---|---|
| **System/HTTP properties** | Object information and HTTP serving behavior | Content-Type, Content-Length, ETag, Last-Modified |
| **User-defined metadata** | Application-added key-value pairs describing the blob | source=mobile, uploadedBy=service-a |
| **Blob index tags** | Indexed key-values for finding blobs by tag using supported features | department=finance, state=approved |

### HTTP properties: serving files in the right format

A WebP image should have **Content-Type: image/webp**, while PDFs typically use **application/pdf**. If a blob is uploaded without setting the proper Content-Type, browsers/clients may render or download the file unexpectedly.

**ETag** supports optimistic concurrency control. Applications can use the **If-Match** condition to write changes only if the blob is still at the version that was read. This is useful when multiple workers or users might update an object.

### Metadata

Metadata is suitable for small descriptions that help systems record data origin or pipeline stage. However, metadata is **not indexed by default for SQL-like querying across an entire container**. To find blobs by a business attribute, use a catalog/index or index tags when appropriate.

Do not place passwords, tokens, sensitive information, or unnecessary personal data in metadata or blob names. Protection policies and metadata read permissions must be evaluated alongside data access permissions.

### Blob index tags

Blob index tags allow attaching and finding blobs based on tag conditions supported by the service. For example, you might want to find files with **state=approved** and **docType=invoice** without manually scanning every blob name.

However, tag indexing has limits on tag count, value types, APIs, support coverage, and cost. Do not treat it as a relational database or full-text search engine. Some account/tier/namespace configurations have feature differences; verify support before choosing tags as a business foundation.

## 9. Is a Blob Name a Business ID?

A blob name can suffice to retrieve an object, but it should not always be used as a unique business identifier.

For example, a user uploads a file named **contract.pdf**. If the application uses this name directly as the key, two users might accidentally create a collision; a user renaming the file also changes the reference.

A better design:

~~~text
DocumentId (database): doc-83b9
OwnerCustomerId: c001
DisplayFileName: contract.pdf
BlobContainer: documents-private
BlobName: customers/c001/doc-83b9/original.pdf
ContentType: application/pdf
Status: uploaded
~~~

When serving a download:

1. Client requests **GET /documents/doc-83b9**.
2. API authenticates the user and checks permissions for **DocumentId**.
3. Backend retrieves the container/blob name from the catalog.
4. Backend returns a stream or short-lived authorized URL meeting security requirements.

This way, renaming the display filename does not force changing the blob name. You can also manage data deletion and auditing using a stable business ID.

For immutable content, you can consider **content-hash-based** naming for deduplication. However, hashing alone does not solve authorization, retention, encryption, or multi-customer ownership of a single object; reference counting and business-level permissions must be designed accordingly.

## 10. Security: Private Containers and Data Access Permissions

Blob URLs are not public by default. For application data, prefer **private containers**, then grant permissions to the appropriate principals.

### Common authorization methods

| Method | When it fits | Notes |
|---|---|---|
| **Microsoft Entra ID + Azure RBAC** | Applications/workloads using managed identities or operators | Prefer least privilege, use appropriate data roles |
| **User delegation SAS** | Need to grant temporary access to blobs/containers based on an Entra identity | Restrict permissions, resource, duration, and HTTPS |
| **Service/account SAS** | Integration scenarios requiring an account-key-signed SAS | Strictly manage keys and token exposure risks; use only when truly needed |
| **Shared Key** | Legacy compatibility or special requirements | Very broad permissions, hard to audit per user; avoid if unnecessary |
| **Anonymous public access** | Only truly public data permitted by policy | Consider CDN, public URLs, and data exposure risks |

To **read blob contents** using Azure CLI/SDK with Entra ID, users typically need a role such as **Storage Blob Data Reader**; to upload, modify, or delete, **Storage Blob Data Contributor** may be needed depending on scope and role capabilities. **Owner/Contributor at the management plane does not automatically grant permission to read blob contents** via the OAuth data plane.

In Azure environments, use **managed identity** for App Service, VMs, Functions, or supported workloads instead of hardcoding account keys in application configuration. When a client needs to directly download a private blob, the backend can issue a **short-lived SAS** after checking business permissions, rather than distributing the entire storage account's key.

### Networking and encryption

- Use policy-approved HTTPS/TLS versions; enable the secure transfer requirement.
- Consider **firewall/network rules** or **Private Endpoint** if only workloads within a private network should have access.
- When using Private Endpoint, verify DNS for the Blob endpoint and network connectivity from the application.
- Blob Storage encrypts data at rest according to the service model; evaluate customer-managed keys if advanced key management is required.
- Keep secrets and SAS tokens out of logs, publicly shared URLs, repositories, or untrusted environments.
- Monitor data access and configuration changes using appropriate logging/auditing services.

### Preventing data leaks through names and links

Do not use blob names like **patients/NguyenVanA/medical-result.pdf** or **users/email@example.com/...**. Even when data is protected, URLs and logs can inadvertently expose identities or business information. Use random/opaque IDs and store original names in a controlled catalog.

## 11. Protecting Against Overwrites, Accidental Deletion, and Unwanted Changes

Good data organization must be paired with a recovery strategy:

| Mechanism | Goal | Notes |
|---|---|---|
| **Blob versioning** | Retain previous versions of a blob when content changes | Consider storage costs of multiple versions and cleanup policies |
| **Blob soft delete** | Provide a window to recover deleted blobs based on retention | Must be enabled with appropriate retention before an incident occurs |
| **Container soft delete** | Protect against accidental deletion of an entire container | Separate from blob soft delete; separate configuration and restore process |
| **Snapshots** | Capture a blob's state at the time the snapshot is taken | Requires maintenance/deletion policies and incurs storage cost |
| **Immutable storage / legal hold** | Restrict modification/deletion for a retention period or legal hold | Apply WORM policies carefully, considering operational impact |
| **Backup/DR** | Recover from data errors, regional outages, or administrative actions | Recovery capabilities depend on service, account type, and design |

Versioning does not turn blobs into a database with cross-object transactions. Soft delete also does not guarantee protection against every data-loss scenario if retention expires or the account itself is mishandled. For critical data, test **restore** procedures regularly and record actual **RPO/RTO**.

### Avoiding accidental overwrites

Suppose an application uploads to the same name **reports/monthly.csv** every month. A new upload can replace the old content. There are two strategies:

1. **Immutable names:** **reports/2026/11/report-20261120-001.csv**; keep each generation separate.
2. **Fixed logical name + versioning/ETag:** keep using **reports/latest.csv**, but enable versioning and use conditional writes when multiple actors update it.

Choose according to needs. For invoices and documents requiring auditability, immutable names and versioning can be convenient; for user avatars, versioned replacement paired with cache invalidation may be needed.

## 12. Access Tiers: Organizing by Access Frequency

For supported block blob types and storage accounts, Azure provides tiers such as **Hot, Cool, Cold, and Archive**. Tiers affect storage pricing, read operation costs, and retrieval requirements.

| Tier | Suitable data pattern | Key considerations |
|---|---|---|
| **Hot** | Frequently accessed images and documents | Storage and operation pricing follow the hot model |
| **Cool** | Infrequently read data that still needs to be online | Retrieval/access fees and minimum retention periods must be factored in |
| **Cold** | Very rarely accessed data that still requires online availability per supported features | Check account type, regional support, and pricing |
| **Archive** | Long-term archival data, almost never accessed | Blobs are offline and require rehydration before reading; involves latency and fees |

Not every tier is available for all blob types, SKUs, redundancies, regions, or features. **Archive is not intended for files that an application needs to read immediately when a user clicks download**.

Total cost calculations must include:

- Storage capacity by tier and redundancy.
- Number of operations (writes, reads, lists, tier changes, etc.).
- Read/retrieval fees, rehydration, and early deletion/minimum retention fees where applicable.
- Data transfer/egress, replication, and related charges.
- Capacity of versions/snapshots/soft-deleted data still retained.

### Lifecycle management

**Lifecycle management policies** can transition tiers or delete objects under service-supported conditions, such as data age or prefix. Example design:

~~~text
Container: temporary-exports
  After business retention period: delete temporary blobs

Container: invoices-private
  New data: Hot
  When access frequency drops: consider Cool/Cold
  When reaching retention limit: handle per retention/compliance policy
~~~

This is a **policy concept**, not directly executable rule JSON. When designing lifecycles, you must check behavior with versions, snapshots, soft delete, immutability, and minimum retention periods to avoid unexpected costs or premature deletion.

## 13. Organizing Data for Application Scalability

Good naming is not just for human readability. It impacts **listing, batch processing, access control, and cost management**.

### Avoiding unnecessary single-name hotspots

For very high concurrent write workloads, evaluate key patterns, access distribution, and current scale limits. Blob Storage supports high scale, but not all request patterns concentrated on the exact same blob behave like workloads distributed across many independent blobs.

**Do not** have thousands of workers overwrite a single **latest.json** blob as a queuing mechanism. Use multiple immutable blobs with an appropriate manifest/index or a dedicated messaging service. Do not blindly add random prefixes to every name if doing so breaks listing by tenant/date; measure actual workloads and follow current performance guidance.

### Designing ingestion → processing → serving

~~~text
Client / data source
       |
       v
Container: incoming-private
  uploads/<opaque-id>.bin
       |
       | Virus scan / validate / parse / transform
       v
Container: processed-private
  customers/<id>/documents/<doc-id>.pdf
       |
       | Business authorization
       v
App API / signed download / internal processing
~~~

User-uploaded files must be treated as **untrusted data**. Separating incoming and processed containers helps pipelines verify actual MIME types, scan for malware, enforce file limits, and track processing states before serving files to other users.

### Catalog and manifest

When an application needs to track:

- Who owns the blob?
- What approval status is assigned to the blob?
- Has the data been processed yet?
- Which batch does each blob belong to?
- Can the blob be deleted upon customer request?

Use a properly designed database catalog or manifest. Prefixes/tags assist categorization but do not replace business indexes or transactions.

## 14. Viewing Containers and Blobs in Azure Portal

Hands-on steps in the portal:

1. Sign in to [Azure Portal](https://portal.azure.com/) and identify your subscription and resource group.
2. Open a storage account type suitable for Blob Storage.
3. Under **Data storage**, select **Containers**.
4. Create a new container, such as **documents-private**, and keep **Private (no anonymous access)**.
5. Open the container and upload a test file containing no sensitive information.
6. Set a blob name like **samples/2026/11/demo.txt** if the upload UI supports the corresponding name/prefix.
7. Inspect Properties, Content type, ETag, access tier, metadata, or tags if available.
8. Browse through the prefix structure to observe **virtual folders**.
9. Inspect Access control (IAM), versioning, soft delete, and protection settings within your required scope.

Menu names or displayed features may vary depending on storage account kind, namespace, and Portal version. If you cannot view data despite seeing the storage account, check **data plane** permissions rather than assuming it is a UI bug.

## 15. Hands-On with Azure CLI: Creating Containers and Organizing Blobs

This lab is intended for an authorized **learning subscription and resource group**. Storage, transaction, and network costs may apply; set budgets or cost controls according to organizational policy. Shell examples use **Bash in Azure Cloud Shell** or a Bash environment with Azure CLI; PowerShell has different variable and line-continuation syntax.

### Prerequisites

- Azure CLI installed and signed in with an account authorized to manage resources for the lab.
- Permission to create a storage account in the chosen region and permission to create blob data.
- A **globally unique** storage account name following the lowercase letters and numbers pattern.
- Sample data containing no PII, tokens, or real documents.

### Step 1: verify subscription and declare variables

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-blob-storage-lab"
LOCATION="southeastasia"
STORAGE_ACCOUNT="stbloblabreplace123"
CONTAINER="documents-private"
~~~

**You must replace** **stbloblabreplace123** with an available storage account name, 3–24 characters using only lowercase letters/numbers. Do not use production names as-is, and verify **SUBSCRIPTION_ID** before creating resources. If organizational policy forbids creating new storage accounts, use a designated lab account where you have been granted permissions instead of modifying shared account settings.

### Step 2: create resource group and storage account

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION" \
  --tags environment=learning purpose=blob-lesson

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2
~~~

**Standard_LRS** uses local redundancy for lab purposes; do not treat it as a suitable DR choice for all production data. In real environments, choose ZRS/GRS/GZRS or other configurations based on availability requirements, regional support, and budget. Creating the account in this example does not automatically enable versioning or soft delete; you must configure them separately to test recovery mechanisms.

### Step 3: create a private container using Entra ID

~~~bash
az storage container create \
  --account-name "$STORAGE_ACCOUNT" \
  --name "$CONTAINER" \
  --auth-mode login \
  --public-access off
~~~

Depending on the account/role, you may encounter **AuthorizationPermissionMismatch** or **AuthorizationFailure**. You need appropriate data plane permissions, such as **Storage Blob Data Contributor**, or an equivalent role/scope. Standard Azure Owner/Contributor roles at the management plane do not automatically grant full OAuth permissions for blob operations. Wait for role propagation before retrying rather than rushing to use account keys to bypass organizational policy.

### Step 4: create sample data and upload under a logical hierarchical name

~~~bash
printf '{"orderId":"order-001","status":"demo"}\n' > order-001.json

az storage blob upload \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "orders/raw/2026/11/20/order-001.json" \
  --file "./order-001.json" \
  --content-type "application/json" \
  --auth-mode login \
  --overwrite false
~~~

The blob name includes **orders/raw/2026/11/20/**. In a flat namespace, you do not need to create physical folders before uploading. The full blob name is **orders/raw/2026/11/20/order-001.json** in the **documents-private** container.

### Step 5: list blobs by prefix

~~~bash
az storage blob list \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --prefix "orders/raw/2026/11/" \
  --auth-mode login \
  --output table
~~~

You should see the uploaded blob if list permissions are appropriate and the previous operation completed. The prefix filters by the **beginning of the blob name**. When there are many results, applications using SDK/REST APIs must handle pagination via continuation tokens; do not assume all data returns in a single response.

### Step 6: inspect properties and download

~~~bash
az storage blob show \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "orders/raw/2026/11/20/order-001.json" \
  --auth-mode login \
  --output json

az storage blob download \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "orders/raw/2026/11/20/order-001.json" \
  --file "./downloaded-order-001.json" \
  --auth-mode login
~~~

Inspect the downloaded file content, Content-Type, and ETag if desired. Do not log account keys or long-lived SAS tokens just for troubleshooting.

### Step 7: observe access permissions

Try opening the blob URL in a private browser window **without a token/SAS**. If the container and account are properly configured as private, the request must not return the blob content merely because the URL is known. Exact HTTP behavior depends on request type and service configuration; do not infer that a single error code replaces checking permissions and network access.

### Step 8: clean up lab resources

Before deleting, verify **RG** is the dedicated lab group and the storage account contains no data that needs to be kept. Delete the entire resource group:

~~~bash
az group delete \
  --name "$RG" \
  --yes

az group exists --name "$RG"
~~~

When the output is **false**, the resource group no longer exists in ARM. Billing data may appear with a delay; check Cost Management if transactions or other billable resources occurred.

**Do not run group deletion commands** on shared or production resource groups. If using an existing account instead of a new lab account, only clean up the blobs/containers created by the lab itself and follow approved procedures.

## 16. Design Scenario: Multi-Tenant Document Storage System

Suppose you are building a SaaS contract storage platform for 300 enterprises. Each customer has users logging in via Microsoft Entra ID, with these requirements:

- Customer A's documents must never be exposed to Customer B.
- Users can upload, list, and download contracts they are authorized to read.
- There is a contract approval workflow and version history.
- Accidentally deleted data must be recoverable within an administrative retention window.
- Older, infrequently accessed documents need cost optimization.

### Proposed data organization

~~~text
Storage account: stcontractsprod
  Container: contract-uploads-private
    tenants/<tenant-id>/incoming/<document-id>/original.pdf

  Container: contract-docs-private
    tenants/<tenant-id>/approved/<document-id>/v1.pdf
    tenants/<tenant-id>/approved/<document-id>/v2.pdf

  Container: contract-exports-private
    jobs/<job-id>/export.csv
~~~

This is a logical layout, not a configuration sufficient by itself for customer isolation. If compliance requirements are strict, evaluate separate accounts/containers, network boundaries, and appropriate encryption keys.

### Secure upload flow

~~~mermaid
sequenceDiagram
  participant U as User
  participant API as App API
  participant DB as Catalog DB
  participant B as Blob Storage
  U->>API: Request to upload contract
  API->>API: Authenticate, identify tenant and permissions
  API->>DB: Create document ID and pending status
  API-->>U: Scoped upload permission or upload via API
  U->>B: Upload to designated blob (if authorized)
  API->>B: Verify blob and validate input data
  API->>DB: Mark uploaded/approved per workflow
  U->>API: Request to download document
  API->>DB: Verify document belongs to tenant and permissions
  API-->>U: Stream or short-lived, narrowly scoped download URL
~~~

In some architectures, the backend performs the upload directly instead of issuing a URL to the client. Regardless of the choice, **the application must authenticate and authorize before issuing upload/download tokens**, restrict destinations, and validate untrusted content.

### Choosing metadata and catalog

| Attribute | Where should it live? | Reason |
|---|---|---|
| Document ID, customer ID, owner ID | Catalog database | Authorization and business queries |
| Blob container/name, version ID | Catalog database | Identify physical storage location |
| Content-Type, size, ETag | Blob properties; optionally synced to catalog | HTTP serving, integrity/concurrency checks |
| Source service, pipeline stage | Metadata if appropriate | Technical traceability |
| Supported tags for finding objects | Blob index tags when suitable | Querying by a simple set of attributes |
| Approval status, contract terms, business retention | Catalog, policies, and compliance workflows | Do not let a single metadata field autonomously decide deletion/reads |

### Lifecycle plan

1. New blobs are uploaded to the private incoming container.
2. Workers inspect the file, validate format, and run security scans as needed.
3. Validated data is placed into the processed/approved tier; the catalog updates status.
4. Versioning/soft delete or an equivalent mechanism is configured per policy.
5. Infrequently accessed data is evaluated for tier transitions via lifecycle policies.
6. Once retention expires and deletion is permitted, the system deletes with controls and audit logging.

A good lifecycle addresses **security, traceability, recovery, and cost**, not just naming conventions.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Azure Portal shows storage account but not blobs | Missing data plane role, network issue, or no list permission | Check Storage Blob Data Reader/Contributor, IAM scope, firewall, role propagation |
| Blob upload returns 403 | Insufficient data RBAC, shared key/SAS blocked, expired SAS, or network rule | Check auth mode, permissions, scope, and logs per policy |
| Blob URL cannot be opened publicly | Private container | Expected behavior; use Entra ID/SAS appropriately |
| Container creation fails due to name | Contains uppercase, underscore, too short, or invalid format | Check naming rules and existing containers |
| Folders not visible after upload | Flat namespace uses virtual folders; wrong prefix or different blob name | Verify exact blob name and list by prefix |
| Conditional metadata search is inefficient | Metadata is not a general query index | Use blob index tags when supported or a separate catalog |
| Upload overwrites old content | Duplicate blob name, overwrite allowed, versioning not enabled | Use immutable names, conditional writes, versioning |
| Client downloads PDF as unexpected file | Incorrect Content-Type | Check Content-Type/Content-Disposition and application handling |
| Old file moved to Archive fails to download | Blob is offline and needs rehydration | Check tier status, rehydration process, and wait time |
| Costs rise despite low app traffic | Many versions/snapshots/soft deletes, tier and retrieval/transaction fees | Check metrics, lifecycle, retention, and cost details |
| Customer A can read Customer B's file | Backend authorization relied on client-supplied prefix, or overly broad container permissions | Audit tenant mapping, data RBAC, SAS scope, and API object authorization |
| Blob deleted but storage still billed | Versions/snapshots/soft-deleted data still within retention | Inspect policies and state of retained versions |
| Private endpoint cannot be reached | Misconfigured DNS/Private Endpoint/network rule | Check private DNS zone, network routing, and firewall |

When troubleshooting, record the account, container, **non-sensitive blob name**, timestamp, operation, HTTP status, request ID, and identity/permission context. Never put access keys, SAS tokens, credentials, or real file contents into logs/tickets.

## 18. Pre-Production Blob Storage Design Checklist

- [ ] Clearly confirm the data fits object storage rather than a database or file share.
- [ ] Select the storage account based on region, redundancy, network/security boundaries, and cost requirements.
- [ ] Design containers around domain, permissions, and lifecycle; avoid arbitrary container sprawl.
- [ ] Ensure blob names are consistent, stable, free of sensitive data, and support prefix listing.
- [ ] Distinguish virtual folders from HNS directories; pick the namespace that matches needs.
- [ ] Choose the right block/append/page blob based on I/O pattern.
- [ ] Maintain a business catalog for ownership, permissions, status, and blob references.
- [ ] Keep containers private; use Entra ID/managed identity and least-privilege data RBAC where feasible.
- [ ] If issuing SAS, restrict resources, permissions, lifetime, protocol, and protect tokens.
- [ ] Control public access, TLS, network rules, Private Endpoints, and DNS as required.
- [ ] Evaluate versioning, blob/container soft delete, backups, immutability, and test restores.
- [ ] Design tiers/lifecycle according to actual access frequency and retention.
- [ ] Monitor storage capacity, transaction counts, access errors, logs, costs, and quotas.
- [ ] Test upload/download, prefix listing, overwrites, recovery, and tenant isolation.
- [ ] Have procedures for cleaning up test data and handling data upon customer offboarding.

## 19. Self-Check Questions

1. What is the difference between a storage account, a container, and a blob? Is a blob name globally unique across all of Azure?
2. Why is Blob Storage usually better suited for product images than storing images directly inside transactional database tables?
3. In a flat namespace, does the path **reports/2026/11/a.csv** create three real directories?
4. When should you choose HNS instead of flat namespace virtual folders?
5. Which workload types fit block blobs, append blobs, and page blobs?
6. Can prefix listing replace a SQL query filtering by approval status?
7. How do metadata and blob index tags differ?
8. Why might a user with the Contributor role on a resource group still be unable to read blob contents via OAuth?
9. In a multi-tenant SaaS, why is the **tenants/t001/** prefix insufficient for data isolation?
10. Based on which cost and operational characteristics do you choose between Hot, Cool, Cold, and Archive?
11. How do versioning and soft delete aid recovery? Why is a backup/DR strategy still needed?
12. When generating a file download URL for a customer, why should you avoid sending an account key or a broad, long-lived SAS?
13. If you want to keep all daily reports, how would you choose the blob naming convention and lifecycle?

## 20. References

- [Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction) — object storage model, containers, and blob types.
- [List blobs with Azure Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-list) — listing blobs, prefixes, and pagination.
- [Manage blob properties and metadata](https://learn.microsoft.com/azure/storage/blobs/storage-blob-properties-metadata) — Content-Type, ETag, and metadata.
- [Find blobs by tags](https://learn.microsoft.com/azure/storage/blobs/storage-manage-find-blobs) — blob index tags and finding objects.
- [Azure Data Lake Storage hierarchical namespace](https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-namespace) — hierarchical directories and related capabilities.
- [Access tiers for blob data](https://learn.microsoft.com/azure/storage/blobs/access-tiers-overview) — Hot/Cool/Cold/Archive and pricing.
- [Authorize access to blobs with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory) — data plane authentication/RBAC.
- [Soft delete for blobs](https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview) — recovering deleted blobs.
- [Lifecycle management overview](https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-overview) — automated tier transitions and age-based data handling.
- [Azure CLI: az storage blob](https://learn.microsoft.com/cli/azure/storage/blob) — upload, list, show, and download.

**Conclusion:** Good Blob Storage organization starts with **storage account/container boundaries**, followed by **blob names/prefixes**, access permissions, and data lifecycle. Displayed folders are not necessarily real folders; prefixes are not an authorization mechanism; metadata is not a search database. Use private containers, stable blob names, a business catalog, protected data, and appropriate lifecycles so your Azure application architecture is scalable, governable, recoverable, and cost-controlled.

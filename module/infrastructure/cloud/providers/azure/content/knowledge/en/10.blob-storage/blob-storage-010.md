# Blob Index Tags, Metadata, and Object Search

> **Chapter:** Object Storage with Blob Storage  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Exploring the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networking, compute services, storage, and data. Learn to deploy, monitor, secure, and control costs for an Azure application architecture.

## Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **blob system properties**, **metadata**, and **blob index tags**.
2. Choose the right object lookup mechanism: by **name/prefix**, by **indexed tags**, or by **document content**.
3. Set, read, and query blob index tags using Azure CLI or the Azure Storage SDK.
4. Write tag filter expressions, understand storage account scope, and distinguish querying the index from reading a specific blob's tags.
5. Explain **eventual consistency** of the tag index, data access permissions, security considerations, and costs.
6. Design naming, metadata, and tagging conventions for a document-processing workflow on Azure.

## 1. The Problem: Finding Documents Across Millions of Blobs

An accounting system uploads invoices, contracts, and reports to Azure Blob Storage. Blobs have names like:

~~~text
storage account: stdocslab001
container:       documents

invoices/2026/01/invoice-0001.pdf
invoices/2026/01/invoice-0002.pdf
contracts/2026/contract-0071.pdf
reports/2026/quarter-1.csv
~~~

The application needs to answer different questions:

- **Name or path:** Which blobs exist under the prefix `invoices/2026/01/`?
- **Descriptive data:** Which source system ingested `invoice-0001.pdf`, and which pipeline generated it?
- **Business classification:** Which documents have `Project=Atlas` and `ReviewStatus=Approved`, regardless of which virtual folder they sit in?
- **Document content:** Do any PDF documents contain the phrase "payment terms"?

These four questions require different mechanisms. **Azure Blob Storage does not automatically full-text index PDF contents**, and standard metadata does not offer server-side querying like blob index tags.

Illustrative storage layout:

| Blob | Metadata | Blob index tags |
| --- | --- | --- |
| `invoices/2026/01/invoice-0001.pdf` | `source=erp`, `pipeline=ingest-v2` | `Project=Atlas`, `ReviewStatus=Approved`, `Year=2026` |
| `invoices/2026/01/invoice-0002.pdf` | `source=erp`, `pipeline=ingest-v2` | `Project=Atlas`, `ReviewStatus=Pending`, `Year=2026` |
| `contracts/2026/contract-0071.pdf` | `source=crm`, `pipeline=contract-sync` | `Project=Orion`, `ReviewStatus=Approved`, `Year=2026` |

The filter `"Project" = 'Atlas' AND "ReviewStatus" = 'Approved'` returns **invoice-0001.pdf**, because the service can use the **tag index** to locate objects. To find every blob with metadata `source=erp`, the application needs another approach, such as listing and reading/filtering metadata or maintaining a separate index.

## 2. Structure of a Blob and Three Types of Information

A **storage account** holds containers; containers hold **blobs**. Each blob has content, a name, and associated descriptive data.

~~~mermaid
flowchart TD
    A["Storage account\nstdocslab001"]
    C["Container\ndocuments"]
    B["Blob\ninvoices/2026/01/invoice-0001.pdf"]
    P["System properties\nETag, Last-Modified, Content-Type"]
    M["User metadata\nsource=erp, pipeline=ingest-v2"]
    T["Blob index tags\nProject=Atlas, ReviewStatus=Approved"]
    I["Blob tag index\nFind Blobs by Tags"]
    A --> C --> B
    B --> P
    B --> M
    B --> T --> I
~~~

### 2.1. System Properties

Azure Blob Storage manages numerous blob properties, for example:

- `Content-Length`: object size in bytes.
- `Content-Type`: media type declared by the uploader or app, such as `application/pdf`.
- `ETag`: version/condition token supporting optimistic concurrency control.
- `Last-Modified`: modification timestamp per service semantics.
- Access tier, lease state, and other properties depending on blob type/configuration.

These fields are **not** user-defined metadata or blob index tags. Several can be read via Get Blob Properties, blob listing, or dedicated APIs. Never hijack `Content-Type` as a mutable business classification label.

### 2.2. User-Defined Metadata

**Blob metadata** consists of application-attached key–value pairs on a blob. Example:

~~~text
source=erp
pipeline=ingest-v2
documentowner=finance-team
ingestedat=2026-11-20T08:30:00Z
~~~

Metadata works well for describing an object's **origin, creation context, and operational provenance**. It is stored alongside the blob, yet **Blob Storage does not index it for filtering via metadata expressions**.

For example, there is no native query equivalent to "find all blobs where metadata.pipeline = ingest-v2" via the tag index service. You can call **List Blobs** by container/prefix requesting metadata where supported by the API/SDK and filter client-side; at large scale, this requires scanning many records.

Metadata is transmitted via HTTP headers formatted as `x-ms-meta-<key>` in applicable REST calls. Metadata has total size caps and naming rules; do not use it to store large JSON payloads or long prose.

### 2.3. Blob Index Tags

**Blob index tags** are also key–value pairs attached to a blob, except Azure Blob Storage maintains a **searchable index** over them. Example:

~~~text
Project=Atlas
ReviewStatus=Approved
Year=2026
Sensitivity=Internal
~~~

Thanks to the index, applications can locate matching blobs **across the entire storage account**—even across different containers or prefixes—using **Find Blobs by Tags**.

Design characteristics:

- Tags are **strings**, not numeric or date columns with automatic type casting.
- Each blob supports **up to 10 index tags**; keys and values have length and character restrictions.
- Keys must be unique within a blob's tag set; key names and values must obey service rules.
- Tag names and values are case-sensitive in comparisons; standardize naming conventions.
- Writing/updating tags and updating the search index can finish at different times: **search results can lag** behind an update.
- Not every storage account kind supports features identically. Verify blob index tags support for your account kind, namespace, API version, and planned services.

**Practical rule:** use tags for **attributes needed in large-scale search filtering**; use metadata for **descriptive blob info that does not need index-based querying**.

## 3. Metadata vs. Blob Index Tags: Comparison Table

| Criterion | Metadata | Blob index tags |
| --- | --- | --- |
| Purpose | Describe blob origin, configuration, and context | Categorize and query blobs by conditions |
| Storage | Key–value pairs attached to the blob | Key–value pairs attached to the blob, separately indexed |
| Server-side key/value query | **No** native metadata search equivalent to Find Blobs by Tags | **Yes**, via Find Blobs by Tags |
| Read on a known blob | Get Blob Properties/Get Metadata | Get Blob Tags |
| Search scope | Usually list blobs in container/prefix then filter, or build an external index | Search across the storage account, optionally filtered by container |
| Data type | Strings stored per metadata rules | Strings; compared per tag query rules |
| Count/size limits | Bounded by total metadata size and HTTP header rules | Up to 10 tags/blob plus per-key/value length limits |
| Cost | Tied to related operations/storage | Can incur index storage, tag update/query, and transaction charges |
| Access permissions | Tied to reading/writing blob properties per operation | Dedicated permissions for reading/writing tags and finding by tags |
| Suitable examples | `ingestionpipeline=etl-v3` | `Project=Atlas`, `State=Approved` |

### Do Not Confuse with Blob Names and Prefixes

Blob names can contain `/` to simulate folder hierarchies, e.g.:

~~~text
invoices/2026/01/invoice-0001.pdf
~~~

In a standard **flat namespace**, this remains a **blob name**; slashes help apps filter by prefix and render virtual folder trees. In accounts with **hierarchical namespace** enabled, folders/paths carry distinct semantics; verify exact feature support.

- `List Blobs(prefix="invoices/2026/")`: searches **by name** starting with the prefix.
- `Find Blobs by Tags("Project" = 'Atlas')`: searches **by indexed labels**.
- Finding the word "contract" inside a PDF: requires a **content indexing service**, such as Azure AI Search or a custom application search index.

## 4. Designing Operational Tag Sets

### 4.1. Pick High-Selectivity Filtering Fields

Because each blob allows only a limited number of tags, never mirror an entire business JSON payload into tags.

Suggestions for a document system:

| Tag key | Example values | Common query |
| --- | --- | --- |
| `Project` | `Atlas` | List all documents for Project Atlas |
| `ReviewStatus` | `Pending` / `Approved` | Find documents awaiting approval |
| `DocumentType` | `Invoice` / `Contract` | Filter by document category |
| `Year` | `2026` | Filter by year using string convention |
| `RetentionClass` | `Standard` / `LongTerm` | Drive data lifecycle policies |
| `Department` | `Finance` / `Legal` | Group documents by business unit |

Supporting metadata:

~~~text
source=erp
uploaderapp=docs-api
pipelineversion=3
importbatch=batch-20261120-a
originalfilename=invoice-supplier-001.pdf
~~~

Never put sensitive data like national IDs, bank account numbers, tokens, passwords, confidential customer data, or full contract text into tags. Tags are operational query labels, not a secret vault.

### 4.2. Naming Conventions Must Be Consistent

Consistent example:

- Keys in **PascalCase**: `Project`, `ReviewStatus`, `DocumentType`.
- Values from a controlled vocabulary: `Pending`, `Approved`, `Rejected`.
- Never mix `approved`, `APPROVED`, and `Approved` for the same meaning.
- Do not rename keys across systems without a data migration plan.
- Add a new tag only for a clear query need or lifecycle rule.

A minor typo like querying `"reviewstatus" = 'Approved'` instead of `"ReviewStatus" = 'Approved'` returns zero results even when blobs hold the right tag under different casing.

### 4.3. Tags Are Always Strings: How to Store Dates and Numbers?

Because tag queries are not a richly typed database engine, **range comparisons (`<`, `>`) use lexicographical string ordering**, not automatic numeric or date casting.

Example:

~~~text
"Priority" = "2"
"Priority" = "10"
~~~

In string comparison, `"10"` and `"2"` do not sort numerically. For range queries, use zero-padded fixed-width strings such as `Priority=02` and `Priority=10`, or use an application index with native numeric types.

For dates, pick year-month-day ordering:

~~~text
ReviewDate=2026-11-20
~~~

And keep formatting uniform (ISO 8601 by design). Never mix `20/11/2026`, `2026/11/20`, and `Nov-20-2026` and expect range comparisons to work accurately.

### 4.4. Tags Are Not Access Control Policies

Setting `Sensitivity=Confidential` **does not make a blob private**. To restrict who can read or edit content, configure authentication, Azure RBAC/ACLs per account capabilities, SAS, network controls, encryption, and real policies.

Applications or governance policies can treat tags as **signals** for classification and routing, but tags are not a standalone firewall or ACL.

## 5. How Does Find Blobs by Tags Work?

Azure Blob Storage provides an operation to search by **blob index tag** filter expressions. The index is scoped to the **storage account**. One query can logically scan across multiple containers in the same account without forcing the application to list every blob.

### 5.1. Basic Filter Expression Syntax

Examples:

~~~text
"Project" = 'Atlas'
"Project" = 'Atlas' AND "ReviewStatus" = 'Approved'
"Year" >= '2025' AND "Year" <= '2026'
@container = 'documents' AND "DocumentType" = 'Invoice'
~~~

Meaning:

1. Find all blobs with `Project=Atlas`.
2. Find blobs belonging to Atlas that are also approved.
3. Filter by string `Year` within a range using uniform formatting.
4. Restrict results to container `documents` with `DocumentType=Invoice`.

Important syntax conventions:

- **Tag keys** in expressions are enclosed in **double quotes**, e.g., `"Project"`.
- **Values** are enclosed in **single quotes**, e.g., `'Atlas'`.
- `AND` combines conditions that must all hold; the service may support additional logical combinations depending on syntax and API version limits.
- `@container` is a special identifier to filter by container, not a user-defined tag.
- Keys and values are case-sensitive under tag comparison rules.
- If special characters appear in expressions, follow exact REST, SDK, or Azure CLI escaping/encoding rules.

**Semantically invalid example:** trying to match `metadata.source = erp` with `"source" = 'erp'` when the blob only has **metadata** `source=erp` and no **tag** `source=erp`. The tag query will not return that blob.

### 5.2. Getting a Specific Blob's Tags vs. Querying the Index

Two distinct scenarios:

- **Container and blob name known:** call **Get Blob Tags** to retrieve that exact object's tag set.
- **Matching blobs unknown:** call **Find Blobs by Tags** to query the account-wide index.

This distinction matters most right after editing tags: reading tags on the specific blob reflects the updated tag set immediately, whereas **the search index may not have caught up yet**.

### 5.3. The Index Is Eventually Consistent

Updates to the blob tag index can be processed **asynchronously**. Therefore:

1. The application sets `ReviewStatus=Approved`.
2. `Get Blob Tags` for that blob can immediately return the new value.
3. `Find Blobs by Tags` shortly afterward may still return stale results or omit the blob.
4. Once the index catches up, queries reflect the update.

**Never design a business transaction requiring "write tag, then immediately see it in index query" without handling index lag.** When immediate post-update reads are needed, retain the container/blob name and use Get Blob Tags or application database state.

### 5.4. Paginated Results

In accounts with many blobs, search results are typically **paginated** by the API/SDK. Never grab only the first page and assume it represents all matches. SDKs usually provide iterators/pagers; iterate through continuation tokens or pagination mechanisms completely.

The tag index is not a database supporting arbitrary joins, group-by aggregations, or fuzzy PDF text search. For complex queries, use an appropriate search or database engine.

## 6. Azure CLI Hands-On: Reading and Writing Metadata/Tags

The commands below are **illustrative learning examples**, not instructions to mutate real production data. `show`/`list`/`filter` commands are read-only; `update` and `set` **modify blobs** and require approval in your lab environment.

Assume the following blob **already exists**:

~~~text
Storage account: stdocslab001
Container:       documents
Blob:            invoices/2026/01/invoice-0001.pdf
~~~

Your account needs appropriate data-plane permissions for each operation. Portal "Contributor" at the resource management level does not automatically grant permission to query or edit all blob tags.

### 6.1. Select the right subscription and storage account

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Switch context only after confirming the assigned subscription.
az account set --subscription "<SUBSCRIPTION_ID>"

# Inspect storage account (management-plane read).
az storage account show \
  --resource-group rg-docs-lab \
  --name stdocslab001 \
  --query "{name:name, kind:kind, sku:sku.name, location:location}" \
  --output json
~~~

Resource names are hypothetical. If the account/blob does not exist yet, do not create out-of-scope production resources; you can work through the simulation in Section 12.

### 6.2. View current blob and metadata

~~~bash
az storage blob show \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json

az storage blob metadata show \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json
~~~

Use `--auth-mode login` only when your Microsoft Entra identity already holds matching data permissions. Otherwise, check role assignments at the proper scope rather than casually falling back to shared account keys.

### 6.3. Update metadata

~~~bash
az storage blob metadata update \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --metadata source=erp pipeline=ingest-v2 \
  --auth-mode login
~~~

**Important takeaway:** setting metadata with a supplied set **replaces all existing metadata**. To preserve existing keys, read first, merge key–value pairs, and update carefully. Never run this example on a blob holding important metadata without checking first.

### 6.4. View blob index tags of an object

~~~bash
az storage blob tag list \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json
~~~

This command retrieves **tags of a known blob name**. On permission errors, verify **tag read permissions**, which are distinct from reading blob content alone.

### 6.5. Write blob index tags

~~~bash
az storage blob tag set \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --tags Project=Atlas ReviewStatus=Approved Year=2026 \
  --auth-mode login
~~~

Then read back:

~~~bash
az storage blob tag list \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json
~~~

**Critical operational warning:** Set Blob Tags submits a **complete new tag set**, **replacing existing tags** rather than auto-merging. If the blob had `RetentionClass=LongTerm` and you call set with only `Project=Atlas`, the old tag is lost. Update workflows must read existing tags first, merge, and guard concurrent updates per API/SDK capabilities.

### 6.6. Find blobs by tags across the storage account

In Bash, you can wrap the expression in outer double quotes and escape inner double quotes for readability:

~~~bash
az storage blob filter \
  --account-name stdocslab001 \
  --tag-filter "\"Project\" = 'Atlas' AND \"ReviewStatus\" = 'Approved'" \
  --auth-mode login \
  --output json
~~~

Add a container constraint:

~~~bash
az storage blob filter \
  --account-name stdocslab001 \
  --tag-filter "@container = 'documents' AND \"Project\" = 'Atlas'" \
  --auth-mode login \
  --output json
~~~

The output lists blobs **currently matching the index at query time**, including container and blob name. Do not treat an empty result right after `tag set` as a definite error; account for index lag.

### 6.7. Search by prefix for comparison

~~~bash
az storage blob list \
  --account-name stdocslab001 \
  --container-name documents \
  --prefix invoices/2026/01/ \
  --auth-mode login \
  --output table
~~~

Differences:

- `blob list --prefix`: matches **blob name**, ignoring `ReviewStatus`.
- `blob filter --tag-filter`: matches **index tags**, without inspecting PDF contents.
- `blob metadata show`: reads **metadata** on a known blob name.

## 7. Python SDK Example: Reading, Updating, and Querying Tags

The Azure Storage SDK supports tags, metadata, and index queries. The example below uses **Azure Identity** to acquire credentials configured for the environment (local developer login or workload/managed identity).

Install packages in an appropriate development environment:

~~~bash
pip install azure-storage-blob azure-identity
~~~

**Illustrative code sample**; never run write calls against production blobs blindly:

~~~python
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

account_url = "https://stdocslab001.blob.core.windows.net"
container_name = "documents"
blob_name = "invoices/2026/01/invoice-0001.pdf"

service = BlobServiceClient(
    account_url=account_url,
    credential=DefaultAzureCredential(),
)
blob_client = service.get_blob_client(
    container=container_name,
    blob=blob_name,
)

# Read properties and metadata of this specific blob.
properties = blob_client.get_blob_properties()
print("Metadata:", properties.metadata)

# Read index tags of the known blob.
tags = blob_client.get_blob_tags()
print("Tags:", tags)

# NOTE: replaces the entire tag set. In production,
# handle concurrency and preserve tags that must be kept.
new_tags = dict(tags)
new_tags["Project"] = "Atlas"
new_tags["ReviewStatus"] = "Approved"
blob_client.set_blob_tags(new_tags)

# Find blobs by index tags across the storage account.
expression = '"Project" = \'Atlas\' AND "ReviewStatus" = \'Approved\''
for item in service.find_blobs_by_tags(filter_expression=expression):
    print(item.container_name, item.name)
~~~

In real applications, also implement:

- **Data-plane permissions** on the identity: read/write only what is necessary.
- **Bounded retries** for network or throttling errors; never loop endlessly on permission errors.
- **Concurrency control** supported by the API/SDK. A simple two-step read–merge–set still risks overwriting concurrent updates from another worker.
- **Pagination/streaming** to handle large result sets.
- **Post-write verification**, while accommodating Find Blobs by Tags index latency.

### 7.1. Updating metadata via SDK

~~~python
# Illustrative sample; this replaces the blob's metadata dictionary.
metadata = dict(blob_client.get_blob_properties().metadata or {})
metadata["source"] = "erp"
metadata["pipeline"] = "ingest-v2"
blob_client.set_blob_metadata(metadata=metadata)
~~~

Tags and metadata are **two separate datasets**. Calling `set_blob_metadata` does not turn metadata keys into blob index tags searchable via `find_blobs_by_tags`.

### 7.2. Listing multiple blobs by prefix via SDK

~~~python
container_client = service.get_container_client("documents")

for blob in container_client.list_blobs(
    name_starts_with="invoices/2026/01/"
):
    print(blob.name)
~~~

This performs **listing by name**, great when naming conventions are stable. If the goal is finding `ReviewStatus=Approved` regardless of prefix, use index tags or an application search index.

## 8. REST APIs and Operation Categories to Understand

You do not need to memorize every HTTP request to use the SDK, yet you should understand they are **distinct Blob Storage operations**:

| Need | REST/SDK operation group | Result |
| --- | --- | --- |
| Read blob content | Get Blob / download | Object payload |
| Read properties + metadata | Get Blob Properties or Get Blob Metadata | HTTP headers, metadata |
| Write metadata | Set Blob Metadata | New metadata set |
| Read tags of specific blob | Get Blob Tags | Current index tags on the blob |
| Write tags | Set Blob Tags | New tag set |
| Find all blobs matching tags | Find Blobs by Tags | Matching blob/container names |
| List by prefix | List Blobs | Objects whose names start with prefix |

Tag operations can require **different permissions** from content reads. In audited workflows, track who is authorized to change classification tags and why.

### 8.1. Update Conditions and Consistency

Updating metadata and updating tags should not be treated as an atomic transaction spanning two distinct field sets. If business rules require updating `ReviewStatus` in a database, metadata, and tags together, build an **orchestration/reconciliation workflow**.

Example:

1. Application writes approval outcome to the business system.
2. Worker updates blob tags in a controlled operation.
3. Worker verifies via Get Blob Tags.
4. Search consumers tolerate tag index lag.
5. On failure, enqueue to a retry queue/incident workflow for reconciliation.

If immediate lookup right after approval is mandatory, use the **business database** as the immediate source of truth; the Blob tag index serves as a secondary query path.

## 9. Permissions and Security When Using Tags

### 9.1. Microsoft Entra, RBAC, and SAS

Azure Blob Storage supports multiple authorization mechanisms, including OAuth via Microsoft Entra ID with Azure RBAC and **Shared Access Signatures (SAS)**. Shared Key works where still permitted, though distributing account keys is rarely the right default.

Permissions to distinguish:

- **Reading blob/data** does not automatically allow **editing tags**.
- **Reading tags** and **writing tags** are distinct authorization goals.
- **Account-wide index queries** require dedicated permissions for Find Blobs by Tags.
- When using SAS, specific permissions for **tag operations** and **find/query tags** must be granted on supported SAS types and resources; never assume a download-only SAS can run tag searches.

With Entra ID/RBAC, check the exact data actions corresponding to `tags/read`, `tags/write`, or filter queries per service docs, along with the assigned scope. Pick appropriate built-in or custom roles after testing rather than granting subscription-wide Owner to "fix a 403."

### 9.2. Tags Do Not Replace Data Protection Mechanisms

For example, tagging a blob `Sensitivity=Confidential` while leaving its container public or issuing an overly broad SAS does not stop unauthorized reads.

Combine:

- Disabling anonymous public access for non-public data.
- Least-privilege RBAC/ACLs or SAS per account kind and business needs.
- Restricting network access, using Private Endpoints where required.
- Data encryption by default plus CMK/Key Vault policies as needed.
- Logging and monitoring access and tag edits if required for audits.
- Keeping **secrets, sensitive identifiers, and confidential legal details** out of tag values.

### 9.3. Never Trust Tags as Absolute Truth Without Write Controls

If end users can arbitrarily set `ReviewStatus=Approved`, an app relying on that tag to "grant download access to approved files" has an authorization vulnerability.

Tag values exist for **filtering and organization**; never base approval or authorization decisions on them without a **trusted system of record** and change controls.

## 10. Object Lifecycle, Automation, and Maintenance Rules

### 10.1. Tags in Lifecycle Management

Azure Blob Storage supports *lifecycle management* rules based on qualifying conditions, where **blob index tags** can act as filter criteria for supported features and blob types.

Business design example:

- Blobs carry `DocumentType=Invoice` and `RetentionClass=Standard`.
- Once age conditions are satisfied, a policy transitions access tiers or deletes per approved retention workflows.
- Documents tagged `RetentionClass=LongTerm` follow separate rules and stricter controls.

**Caution:** Never infer from `RetentionClass=LongTerm` that a blob is under a **legal hold**, immutability policy, or delete lock. Legal preservation controls are separate features that must be configured independently.

### 10.2. Tags Do Not Auto-Update When Metadata Changes

If an application updates metadata `pipeline=ingest-v3`, tags like `Project=Atlas` remain independent. Build update logic if classification tags depend on metadata.

In an ingestion pipeline, decide up front together:

1. Blob name and container.
2. Content-Type and required system properties.
3. Provenance metadata.
4. Search/lifecycle tags.
5. Business database record storing authoritative status and object identifiers.

When any step fails, the pipeline should emit events and support safe idempotent reruns.

### 10.3. Controlling Full-Tag-Set Replacement

Suppose a blob currently holds:

~~~json
{
  "Project": "Atlas",
  "ReviewStatus": "Pending",
  "RetentionClass": "LongTerm"
}
~~~

The app only wants to change `ReviewStatus=Approved`. Calling Set Blob Tags with just one tag:

~~~json
{
  "ReviewStatus": "Approved"
}
~~~

risks **wiping out** `Project` and `RetentionClass`. The app must supply the entire tag dictionary to retain. In multi-worker systems, protect consistency via concurrency conditions or a centralized classification owner per supported API design.

Setting tags does not alter PDF file contents. Even so, tag mutations affect search results, lifecycle rules, and app events; govern them like meaningful data modifications.

## 11. Choosing the Right Search Tool

A sound architecture picks the mechanism matching **the question users ask**.

| Question | Usually best fit | Why |
| --- | --- | --- |
| "List all invoices from Jan 2026 under our path convention." | List Blobs by prefix | Blob names encode date structure |
| "Find all approved Atlas blobs, wherever they live." | Find Blobs by Tags | Server-side indexed tag queries |
| "Check which pipeline ingested a known blob." | Get Blob Metadata | Direct metadata read on a known object |
| "Find every blob with metadata pipeline=ingest-v3." | External index or appropriately scoped list/filter | Metadata has no native index query |
| "Find PDFs mentioning contract payment clauses." | Azure AI Search or content search engine | Blob index tags do not parse PDF text |
| "Query by invoice dollar range joined with customer info." | Business database / schema-rich search index | Blob tags are strings with simple filter operators |
| "Delete/re-tier expired objects per policy." | Blob lifecycle management with supported filters | Automated lifecycle, subject to retention controls |

### Combining Blob Storage and Azure AI Search

An app can store **raw files in Blob Storage** while maintaining a **search index** holding filenames, dates, customers, extracted text, and blob links. Azure AI Search offers content and metadata indexing capabilities depending on pipeline, data source/indexer configuration, and document crackers.

~~~mermaid
flowchart LR
    APP["Upload application"]
    B["Blob Storage\nfile + metadata + tags"]
    TAG["Blob tag index\nFind Blobs by Tags"]
    PIPE["Configured\nIndexer / ETL"]
    SEARCH["Search index\ntext + business fields"]
    CLIENT["Search API"]
    APP --> B --> TAG
    B --> PIPE --> SEARCH
    CLIENT -->|"Filter Project, State"| TAG
    CLIENT -->|"Content / semantic search"| SEARCH
~~~

Do not assume every metadata/tag field automatically appears in Azure AI Search without configuring mappings and indexers. Both indexes solve different problems with separate costs and refresh lifecycles.

## 12. Simulated Lab: Finding Documents by Tags

### 12.1. Sample Dataset

A `documents` container holds four blobs:

| Blob name | Metadata `source` | Tag `Project` | Tag `ReviewStatus` | Tag `Year` |
| --- | --- | --- | --- | --- |
| `invoices/2026/invoice-001.pdf` | `erp` | `Atlas` | `Approved` | `2026` |
| `invoices/2026/invoice-002.pdf` | `erp` | `Atlas` | `Pending` | `2026` |
| `contracts/2026/contract-003.pdf` | `crm` | `Orion` | `Approved` | `2026` |
| `reports/2025/report-004.csv` | `etl` | `Atlas` | `Approved` | `2025` |

No live storage account is needed to work through this exercise.

### 12.2. Task A — Filter by tags

Given expression:

~~~text
"Project" = 'Atlas' AND "ReviewStatus" = 'Approved'
~~~

**Predicted results:** `invoices/2026/invoice-001.pdf` and `reports/2025/report-004.csv`.

Adding:

~~~text
"Year" = '2026'
~~~

**Remaining result:** `invoices/2026/invoice-001.pdf`.

Neither query requires knowing prefixes ahead of time once the tag index is populated and synchronized.

### 12.3. Task B — Search by prefix

List blobs whose names start with:

~~~text
invoices/2026/
~~~

**Results:** `invoice-001.pdf` and `invoice-002.pdf`, regardless of `ReviewStatus`. This shows prefixes and tags answer different questions.

### 12.4. Task C — Search by metadata

A user asks: "Find every blob with metadata `source=erp`."

**Correct answer:** there is no direct blob index tag query for `source` if it only exists in metadata. Options:

- List objects within a bounded scope and inspect metadata to filter (watch scale/cost).
- If queried frequently, promote it to an index tag (within limits) or build a search index/database.
- When adding a new tag to existing blobs, run a **backfill** workflow that preserves existing tags and accounts for index lag.

### 12.5. Task D — A blob just changed from Pending to Approved

Right after updating `invoice-002.pdf`:

- Get Blob Tags returns `ReviewStatus=Approved`.
- Find Blobs by Tags still omits `invoice-002.pdf`.

**Explanation:** this is typical index propagation lag. When immediate status is required, use the transactional store or Get Blob Tags on the known blob. Never spin in an infinite query loop or conclude the write failed from a single empty search result.

### 12.6. Task E — Protecting critical tags

A worker needs to update `ReviewStatus`, while the blob also carries `RetentionClass=LongTerm`. Design the update step.

**Reference answer:**

1. Verify the worker holds appropriate permissions and targets the exact blob.
2. Read the current tag set, including `RetentionClass`.
3. Check approval status in the business database.
4. Merge preserved tags with the new `ReviewStatus` value.
5. Write the full updated tag set using concurrency protection if implemented.
6. Read back to verify and emit an audit event, accepting eventual consistency in the search index.

## 13. Troubleshooting Common Errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `Find Blobs by Tags` returns empty right after setting tag | Asynchronous index updates | Call Get Blob Tags to confirm write, retry after brief delay |
| Query `"status" = 'Approved'` finds nothing | Actual key is `ReviewStatus` (wrong name and casing) | Inspect real tags and enforce consistent conventions |
| Filter command returns expression syntax error | Mismatched quotes, bad escaping, invalid operators, or field names | Check the exact query string passed to API/CLI |
| Can read blob content but cannot query tags | Missing data-plane permissions for tags/filter | Check RBAC data actions or SAS tag permissions |
| Writing `ReviewStatus` wiped out `RetentionClass` | Set Blob Tags replaces the whole tag set | Read, merge, and guard concurrent updates |
| Searching `source=erp` via tag query returns nothing | `source` exists only in metadata | Use list/filter or build an index/add tag |
| Results come from only one container | `@container` filter, wrong account, or missing tags | Verify account scope and filter clause |
| Query `Year >= '2025'` gives unexpected results | Values stored in inconsistent string formats | Normalize year/date strings before comparing |
| Invalid tag value errors | Exceeded tag count, length, or allowed character limits | Check service limits and validate before upload |
| Content search across documents returns empty | Tag index does not parse text/PDFs | Use Azure AI Search or content indexing tooling |
| CLI command hits wrong storage account | Wrong subscription/account context or credentials | Check `az account show`, URL/account, roles, and network |
| Costs rise after bulk tagging | Increased tag updates, index/queries, and transactions | Review Cost Management and activity logs |
| Tag query finds match but user cannot download file | Tag query permissions differ from blob read permissions, or network rules block access | Check blob download permissions and network rules separately |

## 14. Production Design and Cost

### 14.1. Separate Each Field's Purpose

For large document platforms:

- **Blob name/prefix:** stable structural hierarchy such as year/month/project for fast prefix listing.
- **Metadata:** operational context, ingestion source, pipeline version, original filename.
- **Blob index tags:** strictly labels needed for cross-container queries or lifecycle filters.
- **Business database:** transactional state, approval history, user references.
- **Azure AI Search:** full-text document search or rich multi-field queries.

This avoids abusing tags as a relational database or metadata as a search engine.

### 14.2. Cost Estimation

When scaling from hundreds to millions of blobs, account for:

1. **Number of tagged blobs** and index storage charges per current pricing.
2. **Volume of Set/Get Blob Tags**, Find Blobs by Tags, and related list/read transactions.
3. **Update churn:** constantly mutating tags generates extra transactions and indexing load.
4. **Tier/retention needs** and lifecycle rules affecting storage cost.
5. **External search charges** if running Azure AI Search or dedicated databases.
6. **Data transfer volume** across regions, accounts, or networks.

Use the **Azure Pricing Calculator** and **Cost Management** with current pricing for your region, account type, and projected volume. Never assume index tags are completely free or all operations cost the same.

### 14.3. Monitoring Classification Data Quality

Generate periodic reports:

| Check | Purpose |
| --- | --- |
| Percentage of blobs missing `Project` or `ReviewStatus` | Catch ingestion pipelines dropping tags |
| Out-of-vocabulary tag values | Catch `approved`/`Approved`/`APPROVED` drift |
| Tag update failure rate | Spot permission gaps or concurrency collisions |
| Database vs. tag mismatch on sampled blobs | Detect stale or broken search states |
| Matching blob counts over time | Detect anomalies in the index or classification system |
| Cost of tag operations and queries | Optimize query patterns, backfills, and retention |

If using tag query results to trigger bulk deletions or tier transitions, enforce approval/target verification steps and recovery mechanisms per data policy.

## 15. Self-Check Questions

**Question 1.** A blob has metadata `source=crm` but no tag named `source`. Will querying `"source" = 'crm'` via Find Blobs by Tags find the blob?

**Answer:** No, because Find Blobs by Tags searches only **index tags**. Metadata is not automatically indexed there.

**Question 2.** A blob is named `invoices/2026/01/a.pdf`. You need to list all blobs under `invoices/2026/`; what should you use?

**Answer:** List Blobs with prefix `invoices/2026/`. That filters by name and does not require tags.

**Question 3.** Right after Set Blob Tags succeeds, a Find query still misses the blob. Is this definitely an error?

**Answer:** No. The tag index experiences asynchronous propagation lag; verify with Get Blob Tags, and check account/scope and filter syntax.

**Question 4.** Why shouldn't a user-editable `ReviewStatus=Approved` tag serve as the sole authorization check for downloading documents?

**Answer:** Tags are classification labels editable by principals with tag-write rights. Approval and authorization decisions should rely on trusted business records and proper authorization controls.

**Question 5.** Why shouldn't you store `Priority=1`, `Priority=2`, `Priority=10` and use string comparison to infer numeric priority?

**Answer:** Tags are strings compared lexicographically without numeric casting. Reliable ordering requires fixed-width encoding like `01`, `02`, `10`, or a numerically typed index.

**Question 6.** What bug can occur if you update tags with only `ReviewStatus=Approved` on a blob that already has `RetentionClass=LongTerm`?

**Answer:** Set Blob Tags can replace the entire tag set, wiping out `RetentionClass`. You must preserve and re-submit existing tags to keep while handling concurrent updates.

**Question 7.** To find PDF documents containing the text "shipping fee", choose Find Blobs by Tags or Azure AI Search?

**Answer:** For searching inside PDF content, choose a content indexing pipeline such as Azure AI Search or an equivalent tool. Find Blobs by Tags only filters labels attached to objects.

**Question 8.** Can you query tags across multiple containers?

**Answer:** Yes, within **a single storage account** where Find Blobs by Tags is authorized; use `@container` to narrow scope if needed. Queries do not span multiple storage accounts automatically.

## Key Takeaways

- **Metadata** describes objects; **blob index tags** are Azure-indexed labels for server-side object filtering.
- **Blob name/prefix**, **metadata**, **tags**, and **file content** represent four distinct lookup capabilities.
- `Get Blob Tags` reads tags for **one known blob**; `Find Blobs by Tags` discovers **unknown blobs** matching conditions.
- The tag index is **eventually consistent**, and tags are **strings**, requiring standardized keys, values, and date/number formatting.
- **Set Blob Tags** replaces **the entire tag set**: preserve critical tags and guard concurrent updates.
- Tag limits, dedicated read/write/query permissions, data security, costs, and approval workflows must all be factored into production deployments.

# Metadata, Versioning, Access Tiers, and Data Lifecycle in Azure Blob Storage

## 1. Problem Statement and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice connecting Spring Boot applications to managed services on **AWS, Azure, and Google Cloud**, using the respective Spring Cloud/Azure SDK libraries while configuring identity, access permissions, secret protection, and integration testing. This lesson belongs to the **Azure Storage** chapter and answers an essential operational question: once a blob has been uploaded, how do we **describe, track, restore, tier, and delete data at the right time**?

Consider an enterprise contract storage system:

- Each PDF contract is stored in the private `documents` container.
- The application needs to know what type of file it is, how large it is, and when it was last modified.
- When a user accidentally overwrites a document, an administrator must be able to restore the previous version.
- New documents are accessed frequently; older documents are rarely read yet must be retained for several years.
- After the retention period, data can be deleted per policy unless a special hold requires keeping it.

**Metadata, versioning, access tiers, and lifecycle management** address different parts of this problem. They complement one another, but do not replace the **business database, backups, authorization, and recovery testing**.

After this lesson, you will be able to:

1. Distinguish **system properties**, **user-defined metadata**, **blob index tags**, and business data in the database.
2. Understand **ETags**, **version IDs**, **snapshots**, **soft delete**, and **immutability/retention**; choose appropriate protection mechanisms.
3. Compare **Hot, Cool, Cold, and Archive** by access frequency, latency, retrieval cost, and minimum retention period.
4. Author **lifecycle management policies** to tier/delete blobs by age and understand the limits of background execution.
5. Apply Spring Cloud Azure/Azure Storage SDK for metadata operations, concurrent update control, reading tier status, and tier transitions.
6. Design integration tests, monitor costs, and avoid deleting or moving documents into Archive when fast retrieval is still required.

## 2. Classifying Information Attached to a Blob

A blob has **byte content** (PDF, image, video, export data), service-managed **properties**, custom **metadata**, and optionally **index tags**. Choose the right place to store each item because each has different access and query mechanisms.

| Component | Examples | Source/Characteristics | Used For |
|---|---|---|---|
| Blob content | Bytes of `contract-42.pdf` | Uploaded/downloaded via Blob API | Storing the actual document |
| **System properties** | `Content-Length`, `Content-Type`, `Last-Modified`, `ETag`, access tier | Managed by Storage or updated via dedicated operations | Serving HTTP, checking versions, observing state |
| **Custom metadata** | `documentType=contract`, `source=portal` | Application-declared key-value pairs | Lightweight technical descriptors read alongside blob properties |
| **Blob index tags** | `department=finance`, `retentionClass=long` | Indexed key-values for querying/filtering where supported | Finding and filtering blobs by tag; lifecycle policy filtering |
| **Business database** | `ownerId`, `tenantId`, approval status, permissions | Application-managed with dedicated schema/indexes/transactions | Business queries, relational links, authorization checks |

Blob metadata is **not an indexed database searchable across arbitrary fields**. If you need to find "all accounting department contracts approved in Q3," use a database or dedicated search/index service. Blob index tags have their own query capabilities, yet still impose limits on tag count, data types, permissions, and operation costs; they do not replace all database capabilities.

### 2.1. Properties Worth Watching

Attributes commonly read:

- **Content-Type**: MIME type used when downloading, e.g., `application/pdf`. Do not trust client-declared MIME types without inspecting content.
- **Blob size**: byte length of the blob content.
- **Last-Modified**: timestamp when Storage recorded the most recent modification to the resource.
- **ETag**: state token for conditional `If-Match` or `If-None-Match` requests.
- **Access tier**: current storage tier or tier attributes related to rehydration/transition status.
- **Version ID**: version identifier when versioning is enabled and supported by the operation.
- **Metadata map**: descriptive key-value pairs attached to the blob.

An ETag **is not a checksum or a version ID**: it supports conditional comparisons on a resource. To verify bytes end-to-end, store an application-computed SHA-256 hash and run dedicated verification checks.

### 2.2. How Do Metadata and Blob Index Tags Differ?

Example of a blob with:

~~~text
Blob name: documents/2026/contract-42.pdf
System property:
    Content-Type: application/pdf
    Content-Length: 284931
    ETag: "0x8E123456789ABCD"
Metadata:
    documentType: contract
    uploadChannel: portal
Index tags:
    department: finance
    retentionClass: long
Database:
    documentId: 42
    ownerId: user-117
    status: APPROVED
~~~

This is **illustrative** data, not output read from a real Azure account.

- **Metadata** suits rarely changing descriptive details typically read once the blob name is known. The SDK returns metadata via `getProperties()`.
- **Index tags** are indexed by Azure Storage to support finding blobs by tag expressions when features and roles permit. Azure lifecycle management can use tag filters alongside prefixes.
- **The database** holds access permissions, business relationships, and workflow state. Never use metadata or index tags as the **sole source of authority** deciding whether a user can download a document.

Metadata names must follow Azure Storage rules; avoid spaces, special characters, or invalid keys. Never put tokens, passwords, or sensitive identifiers in metadata/tags because they may surface in admin operations, SDK responses, logs, or other access channels.

## 3. Metadata Operations with Azure Storage SDK for Java

### 3.1. Reading Properties and Metadata

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
BlobProperties properties = blob.getProperties();

System.out.println("Content-Type: " + properties.getContentType());
System.out.println("Byte size: " + properties.getBlobSize());
System.out.println("ETag: " + properties.getETag());
System.out.println("Last modified: " + properties.getLastModified());
System.out.println("Access tier: " + properties.getAccessTier());
System.out.println("Metadata: " + properties.getMetadata());
~~~

`getProperties()` makes one request to Storage without downloading the PDF's bytes. For large files, reading only properties to display details is far better than downloading the blob into RAM just to check its size.

### 3.2. Writing Metadata

~~~java
import java.util.Map;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
blob.setMetadata(Map.of(
        "documentType", "contract",
        "uploadChannel", "portal"
));
~~~

**Critical point:** `setMetadata(...)` **replaces the entire existing custom metadata**, rather than merely appending two new keys. The example above will wipe out any other metadata keys that already existed. Metadata does not alter content bytes, yet modifying metadata changes resource state and can affect ETags and concurrency.

### 3.3. Conditional Metadata Updates to Avoid Losing Data

Suppose worker A adds `documentType` while worker B adds `uploadChannel`. If both read the old metadata and call `setMetadata`, the second write can erase the key added by the first.

To protect against this, we:

1. Read properties containing the **ETag and metadata map**.
2. Clone the map and update only the desired field.
3. Call `setMetadataWithResponse` with **`BlobRequestConditions.setIfMatch(etag)`**.
4. If Azure returns **412 Precondition Failed**, reload the latest state and **merge under control**; never silently overwrite existing metadata.

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;
import com.azure.storage.blob.models.BlobRequestConditions;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

public static void updateMetadataIfUnchanged(
        BlobClient blob, String key, String value) {

    BlobProperties before = blob.getProperties();
    Map<String, String> merged =
            new HashMap<>(before.getMetadata());
    merged.put(key, value);

    BlobRequestConditions conditions = new BlobRequestConditions()
            .setIfMatch(before.getETag());

    blob.setMetadataWithResponse(
            merged, conditions, Duration.ofSeconds(30), Context.NONE);
}
~~~

This snippet performs **one conditional update**. In a real application, catch `BlobStorageException`, handle 412 with bounded retries **after reloading metadata** when merging is safe; never strip `If-Match` just to "make errors go away". Frequent metadata updates can increase contention with content updates; for rapidly changing data, consider keeping it in the database.

### 3.4. Attaching Blob Index Tags

~~~java
import java.util.Map;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
blob.setTags(Map.of(
        "department", "finance",
        "retentionClass", "long"
));
~~~

Tags and metadata have distinct APIs, limits, permissions, and purposes. `setTags` replaces the tag set per the service API; if preserving prior tags is required, implement merging and concurrent update handling separately. Do not assume all storage accounts/blob types uniformly support tag operations or lifecycle filters; verify configuration and SDK version.

## 4. Versioning: Preserving History When Blobs Change

When **Blob versioning** is enabled on a supported storage account, Azure preserves previous versions of a blob whenever applicable operations modify it. Applications can access data written earlier and restore it if a user accidentally overwrites a file.

~~~mermaid
flowchart TD
    N[Current Blob: contract-42.pdf] --> C[Current version v3]
    N --> P2[Previous version v2]
    N --> P1[Previous version v1]
    C -->|Content users currently see| App[Spring Boot API]
    P2 -->|Select version to restore| Restore[Restore workflow]
    P1 -->|Audit/reconciliation| Audit[History review]
~~~

### 4.1. Version ID, ETag, and Snapshots

| Concept | How It Is Created | Primary Value |
|---|---|---|
| **Current blob** | Current active content for the blob name | Serves day-to-day requests |
| **Previous version** | Automatically recorded by Azure versioning when a blob changes | Accessing/restoring earlier content |
| **Version ID** | Service-generated ID referencing a specific version | Reading, copying, or managing a pinned version |
| **Snapshot** | Point-in-time capture taken by an app/admin request | Intentional recovery point |
| **ETag** | State token of the requested resource or version | Concurrency condition on read/write operations |

**Versioning and snapshots are not equivalent.** Versioning automatically builds history per service configuration; snapshots require an explicit creation call. Both can incur storage costs. Azure Blob Storage versioning has compatibility constraints, such as by account type, hierarchical namespace, or specific features; always verify your deployment account's eligibility.

### 4.2. Example of Writes and Versions

~~~text
Time        Operation                          Illustrative Result
09:00       Upload v1 (10 pages)               Current = v1
09:15       Overwrite PDF with v2 (12 pages)   Current = v2; v1 retained
09:20       Mistaken overwrite with v3 (2 pg)  Current = v3; v1/v2 remain in history
09:30       Choose to restore v2               Copy v2 into a new current (v4)
~~~

When restoring, select **the exact version ID** and use a Storage-supported copy/restore mechanism to create a **new current version** rather than mutating a previous version directly. Verify copy preconditions, source read/destination write permissions, and copy status. Do not rely on labels like "v2" from examples, as real version IDs are service-generated.

### 4.3. Accessing a Specific Version

The Azure Storage SDK for Java provides a client referencing a specific blob version. API illustration:

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.OutputStream;

BlobClient current =
        container.getBlobClient("documents/2026/contract-42.pdf");
String versionId = "<version-id-provided-by-azure>";

BlobClient older = current.getVersionClient(versionId);
// output is an OutputStream created and lifecycle-managed by the caller.
older.downloadStream(output);
~~~

This code assumes `versionId` was obtained from the version-listing API and the account has versioning properly enabled. If your chosen SDK version offers a different overload for version access, use the method supported in that version's documentation. A previous version may have its own tier/state; never assume every version is online or immediately readable.

**Do not treat versioning as a complete standalone backup.** Account deletion, compromised admin permissions, misconfigured retention, or lifecycle policies deleting versions too early can still make data unrecoverable. For critical data, plan external data protection and recovery strategies beyond versioning alone.

## 5. Soft Delete, Snapshots, Retention, and Immutability

Different protection mechanisms serve different goals:

| Mechanism | Purpose | When Useful | Limitations |
|---|---|---|---|
| **Blob soft delete** | Enables restoring deleted blobs or related versions within a configured retention window | Accidental file deletion | Past the retention window or for unsupported operations, data cannot be recovered |
| **Blob versioning** | Retains older versions after updates | Accidental overwrites, content history tracking | Increases stored data; lifecycle policies can delete older versions |
| **Snapshot** | Creates a point-in-time recovery marker | Before major migrations/conversions | Must be created and managed explicitly |
| **Container soft delete** | Enables restoring an accidentally deleted container within its retention period | Administrative operational mishaps | Different scope from blob soft delete |
| **Immutability policy / legal hold** | Restricts modification/deletion of data per retention rules | Data legally protected against tampering/deletion for a mandated term | Can block lifecycle deletes and routine admin operations |

**Soft delete does not stop an authorized principal from issuing a delete command**; it allows recovery per policy. **Immutability** is what enforces modification/deletion restrictions when compliance demands it. To satisfy specific regulations, verify the policy type, scope, lock state, and operational procedures rather than assuming defaults guarantee compliance.

### 5.1. Example Protection Design for Contracts

- Enable **versioning** to prevent content loss on overwrites.
- Enable **blob soft delete** with a window long enough for incident detection/response.
- Apply a **lifecycle policy** to older versions so costs do not grow unbounded, without setting expiration shorter than recovery requirements.
- For records requiring immutability, evaluate **immutable storage** and separate containers/prefixes by policy.
- Regularly **test restoring** a blob or previous version in a non-sensitive environment.

Versioning, soft delete, and immutability can interact; individually reasonable policies may behave unexpectedly when combined. Test against your actual account configuration, especially delete, restore, and archive operations.

## 6. Access Tiers: Hot, Cool, Cold, and Archive

**Azure Blob Storage access tiers** optimize total cost across storage capacity and data access. For block blobs on supported storage account types, consider:

| Tier | Data Access | Suitable Usage Pattern | Key Trade-Off |
|---|---|---|---|
| **Hot** | Online, direct read | Newly created, frequently accessed data | Higher per-capacity storage price than cooler online tiers |
| **Cool** | Online, direct read | Infrequently read data needing fast retrieval when required | Higher access/retrieval fees and minimum retention than Hot |
| **Cold** | Online, direct read | Very rarely read data still needing online response | Lower storage price, higher access/retrieval cost than Cool; longer minimum retention |
| **Archive** | **Offline**; must rehydrate before normal reading | Long-term storage with very rare access | Retrieval requires rehydration workflow, latency can be hours, and incurs fees |

There is no "colder is always cheaper" rule for **total cost**. Archive offers low per-GiB storage rates, but frequent retrievals or repeated tier transitions can push retrieval, operation, and wait costs above Hot.

### 6.1. Minimum Retention and Early Deletion Charges

For tiers billed under standard models, typical minimum retention periods are:

- **Hot:** no minimum early-deletion retention requirement like cooler tiers.
- **Cool:** roughly **30 days**.
- **Cold:** roughly **90 days**.
- **Archive:** roughly **180 days**.

Deleting or moving a blob out of a tier before its minimum duration may incur an **early deletion charge** for the remaining days. These figures are planning guidelines; confirm against **Azure pricing** for your region, redundancy, account type, and deployment date. Never create a "tier every week" policy while ignoring these charges.

### 6.2. The Archive Case

A blob in the **Archive** tier cannot be read directly like a Hot/Cool/Cold blob. It must be **rehydrated** by transitioning to a supported online tier or running an appropriate copy/rehydrate operation. This process is **asynchronous**, can take several hours, and depends on rehydrate priority, blob size, and service characteristics.

When designing a download API:

1. Read the blob's properties/tier.
2. If the tier is online, allow download per permissions and business rules.
3. If archived, trigger a **restore request/job** or rehydrate workflow.
4. Return a **PENDING_REHYDRATION** status with clear user expectations instead of trying to open a stream and reporting "404".
5. Monitor rehydration status, handle failures/timeouts, and issue download links only once the blob is online.

Remember that data still in Archive may incur rehydration fees and minimum retention fees; tier transitions do not replace access-control policies.

### 6.3. Choosing Tiers Across a Product Lifecycle

~~~mermaid
flowchart LR
    N[Newly created file] --> H[Hot: frequent access]
    H -->|After period of low use| C[Cool: online, infrequent reads]
    C -->|Continues infrequent| D[Cold: online, very rare reads]
    D -->|Long-term storage, no fast read needed| A[Archive: offline]
    A -->|Restore requested| R[Rehydrate to online tier]
    R --> U[Allow reads once ready]
~~~

This is an **optional** progression—not every blob must pass through all four tiers. Active transactional documents may stay in Hot for a long time; long-term backups can move from Hot/Cool to Archive when policies and service capabilities allow.

## 7. Account-Level vs. Blob-Level Access Tiers

On storage accounts supporting access tiers:

- An account-level **default access tier** can apply to blobs without an explicitly assigned tier.
- Individual block blobs can have a **specific tier** set within the account type's feature limits.
- **Blob properties** report the current tier status; rehydration progress may appear in additional properties while transitioning out of Archive.
- Some configurations (**premium storage**, hierarchical namespace, page/append blobs, or specialized features) do not share the same tier mechanics as **standard block blobs**. Do not assume every storage account supports Archive.

Azure Java SDK example:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.AccessTier;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
blob.setAccessTier(AccessTier.COOL);

var current = blob.getProperties();
System.out.println("Current tier: " + current.getAccessTier());
~~~

This call **changes storage state and may incur costs**; invoke it only when business/operational workflows intentionally transition tiers. Never put `setAccessTier` inside every user download request, as it adds redundant operations and unexpected charges.

When transitioning from Archive back to online, do not expect `setAccessTier(AccessTier.HOT)` to make the blob readable immediately in the same request. The application must track rehydration completion before serving content.

## 8. Lifecycle Management: Automated Tiering and Deletion

**Azure Blob Storage lifecycle management** applies policies based on conditions such as **blob age**, **prefix**, and **index tags** (where supported) to transition tiers or delete old data. Policies reduce manual work, yet execute as a **background job**—not a scheduler guaranteed to finish at minute 30 of a given day.

### 8.1. Sample Policy

Suppose the `documents` container holds files heavily used for the first 30 days, rarely read after three months, and archived long-term after one year:

- After **30 days** since last modification: move to **Cool**.
- After **90 days**: move to **Cold**.
- After **365 days**: move to **Archive**, if eligible.
- After **730 days**: delete current blob **if retention rules allow**.
- Previous versions and snapshots are governed by separate age thresholds.

Declarative Azure Storage Lifecycle Management JSON policy example:

~~~json
{
  "rules": [
    {
      "enabled": true,
      "name": "documents-retention",
      "type": "Lifecycle",
      "definition": {
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["documents/"]
        },
        "actions": {
          "baseBlob": {
            "tierToCool": {
              "daysAfterModificationGreaterThan": 30
            },
            "tierToCold": {
              "daysAfterModificationGreaterThan": 90
            },
            "tierToArchive": {
              "daysAfterModificationGreaterThan": 365
            },
            "delete": {
              "daysAfterModificationGreaterThan": 730
            }
          },
          "snapshot": {
            "delete": {
              "daysAfterCreationGreaterThan": 180
            }
          },
          "version": {
            "delete": {
              "daysAfterCreationGreaterThan": 365
            }
          }
        }
      }
    }
  ]
}
~~~

**This is an illustrative example**, not a default policy to apply blindly in production. Verify compatibility of **`tierToCold`, version actions, and conditions** with your storage account/region/API. For data with longer retention mandates, adjust deletion ages accordingly. Never deploy a 730-day delete template for records that must be retained for 5–10 years.

### 8.2. How Azure Evaluates Conditions

- **`baseBlob`** applies to the current blob; actions follow age and policy rules.
- **`snapshot`** and **`version`** are separate resources with separate actions. Deleting the base blob does not automatically delete versions/snapshots on the same schedule.
- **`prefixMatch`** filters by **container/blob name prefix**; `documents/` targets names inside the `documents` container. Verify naming patterns before applying broad policies.
- **Blob index tags** enable filtering on tags where supported by the account/feature; ideal for separating `retentionClass=short` and `retentionClass=long` without creating dozens of containers.
- **Age since modification** differs from **age since creation**. Updates can reset the base blob's modification clock; never assume "a file uploaded three years ago will auto-delete" if updates keep refreshing its modified timestamp.

Lifecycle evaluation runs asynchronously; how **multiple overlapping rules** apply can depend on service precedence/logic. Author clear, non-conflicting rules and test them on a test dataset before rolling out broadly.

### 8.3. Differences Between Lifecycle Policies and Spring Boot Scheduled Jobs

| Criterion | Azure Lifecycle Policy | Spring Boot Scheduled Job |
|---|---|---|
| Execution engine | Azure Storage service | Your application/worker |
| Driven by | Age, prefix, tags, and Azure-supported actions | Any business rule your code can query |
| Strengths | Manages large datasets without the app listing/deleting blobs individually | Checks databases, approvals, exceptions, and business workflows |
| Limitations | Cannot express logic like "delete only after contract closes and is approved" | Must operate the scheduler, handle paging, retries, permissions, and state |

A sound design can combine both: the app assigns **`retentionClass`** or business flags; lifecycle handles straightforward age/tier technical rules; and a reconciliation job catches unreferenced data or actions blocked by policies.

## 9. Spring Boot Example Managing Metadata and Tiers

### 9.1. Maven Dependencies

When using Spring Cloud Azure, pick the **BOM compatible with your project's Spring Boot version**. Never fix arbitrary versions:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure.version` must be defined in the POM or corresponding dependency management.

### 9.2. application.yml

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  blob:
    documents-container: ${DOCUMENTS_CONTAINER:documents}
~~~

This example uses default Azure Identity per Spring Cloud Azure configuration. On Azure, prefer **managed identity**; locally, developer identity via Azure CLI works. The storage account and container must be pre-provisioned. Never commit account keys, client secrets, or SAS tokens to Git.

### 9.3. Service Reading Info and Conditionally Updating Metadata

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.AccessTier;
import com.azure.storage.blob.models.BlobProperties;
import com.azure.storage.blob.models.BlobRequestConditions;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentBlobLifecycleService {
    private final BlobContainerClient container;

    public DocumentBlobLifecycleService(
            BlobServiceClient serviceClient,
            @Value("${app.blob.documents-container}") String containerName) {
        this.container = serviceClient.getBlobContainerClient(containerName);
    }

    public BlobSummary describe(String authorizedBlobName) {
        BlobProperties props = blob(authorizedBlobName).getProperties();
        return new BlobSummary(
                props.getBlobSize(),
                props.getContentType(),
                props.getETag(),
                String.valueOf(props.getAccessTier()),
                props.getMetadata());
    }

    public void updateDocumentType(
            String authorizedBlobName, String documentType) {
        BlobClient target = blob(authorizedBlobName);
        BlobProperties old = target.getProperties();

        Map<String, String> merged = new HashMap<>(old.getMetadata());
        merged.put("documentType", documentType);

        BlobRequestConditions condition = new BlobRequestConditions()
                .setIfMatch(old.getETag());
        target.setMetadataWithResponse(
                merged, condition, Duration.ofSeconds(30), Context.NONE);
    }

    // Only call when operational policy permits moving tiers.
    public void moveToCool(String authorizedBlobName) {
        blob(authorizedBlobName).setAccessTier(AccessTier.COOL);
    }

    private BlobClient blob(String authorizedBlobName) {
        return container.getBlobClient(authorizedBlobName);
    }

    public record BlobSummary(
            long size, String contentType, String etag,
            String tier, Map<String, String> metadata) {
    }
}
~~~

**Intentional limitations of the example:** `authorizedBlobName` must be obtained **after the application layer verifies `documentId`, owner/tenant, and access permissions**; never let clients pass arbitrary blob names into this service. The sample does not yet catch 412 errors, enforce tier-operation authorization, or manage rehydration workflows. It demonstrates SDK mechanics, not a complete production admin endpoint.

Real applications should separate **property-reading APIs**, **business-metadata update APIs**, and **tier/retention admin jobs** with appropriate identities/roles. Having Blob write/delete permissions does not mean web users should choose storage tiers or trigger deletions directly.

## 10. End-to-End Lifecycle Design

One way to structure a multi-stage contract storage system:

~~~mermaid
flowchart TD
    U[User uploads PDF] --> A[Spring Boot API]
    A -->|Blob + technical metadata| B[(Private Blob Container)]
    A -->|documentId, owner, retentionClass| DB[(Database)]
    B --> V[Versioning + Soft Delete]
    DB --> P[Business retention/deletion rules]
    P --> L[Lifecycle Policy by prefix/tag/age]
    L --> T{Storage Tier}
    T --> H[Hot / Cool / Cold: online]
    T --> AR[Archive: offline]
    AR -->|When read is needed again| R[Rehydration job]
    R --> H
    P --> X[Check retention/hold policy before delete]
~~~

### 10.1. Business Decisions Before Applying Policies

1. **Classify data:** frequently accessed documents, closed cases, legally mandated records, or temporary files.
2. **Define ownership and business expiration dates:** store in the database; never guess solely from filename or upload date.
3. **Choose prefixes/containers/tags:** e.g., `documents/active/` and `documents/archive-eligible/` or `retentionClass=long`.
4. **Enable protection mechanisms:** versioning, soft delete, backup/restore, and immutability where appropriate.
5. **Design tier and deletion policies:** account for access patterns, recovery SLAs, early deletion fees, and minimum retention.
6. **Test policies with aged mock data, versions, and snapshots:** validate before enabling in production.
7. **Monitor continuously:** tier distribution, rehydration readiness, old version volume, storage/transaction costs, and Archive read errors.

A meaningful **`retentionClass`** must come from controlled business rules. Never allow users to submit `retentionClass=short` to purge a contract early, nor rely solely on tags when determining legal compliance.

### 10.2. Restoring an Overwritten Document

Recommended workflow:

1. User reports wrong content and supplies `documentId`.
2. Backend checks requester permissions and restore approval workflow.
3. Administrator lists versions (by blob name) with corresponding version IDs and timestamps.
4. Verify the correct content in the older version and check that version's tier/online state.
5. Copy/restore the selected version into a new current version **using conditional operations** if needed to avoid overwriting a concurrent edit.
6. Record an audit log with `documentId`, actor, source version, new current version/ETag, and reason.

Do not delete all older versions simply because "the restore succeeded"; they may still be needed for audit trails or subsequent rollbacks.

## 11. Authentication, Authorization, and Data Protection

| Component | Permissions to Check | Risk If Misconfigured |
|---|---|---|
| Property-reading/download API | `Storage Blob Data Reader` at appropriate scope | Cross-tenant content/metadata leaks |
| Metadata-writing/upload API | `Storage Blob Data Contributor` or suitable custom role | Could modify/delete blobs beyond business intent |
| Tier-changing/deletion job | Data-plane permissions for those actions, tightly scoped | Mass archiving or deletion from buggy logic |
| Lifecycle policy administration | Management-plane permission to configure lifecycle on storage account | Broad impact across many containers/blobs/versions |
| End users | Application authorization by `documentId`/owner/tenant | Knowing a blob name without authorization to read |
| Azure Files / Queue | Dedicated service roles and semantics | Mistakenly assuming Blob RBAC applies to Files/Queue |

Prefer **Microsoft Entra ID + managed identity** for apps on Azure. If issuing **SAS** URLs for direct downloads, grant read permission for **the exact blob**, with a short expiration, after backend authorization checks; never log SAS tokens or send account keys to clients.

**Immutability policies/legal holds** can block deletions or edits even when a principal holds Blob Data Contributor. They are a separate safeguard layer from IAM. Storage firewalls/private endpoints and TLS are also independent of RBAC roles; valid RBAC can still be blocked by networking.

## 12. Cost, Latency, and Operational Observability

Tier/lifecycle decisions should be based on **total cost**:

~~~text
Approximate total cost =
    stored capacity by tier and duration
  + read/write/list/set-tier request operations
  + retrieval/rehydration fees (if applicable)
  + early deletion charges (if violating minimum retention)
  + network egress and related operational overhead
~~~

Example with the same 100 GiB file:

- Read daily by an analytics API → Hot may fit due to high read frequency.
- Read 1–2 times per quarter needing instant response → Cool/Cold is worth evaluating.
- Retained for 7 years, almost never read, able to wait hours on restore → Archive may optimize storage, provided you build rehydration workflows and budget fees.

Never compare solely by **GiB/month unit storage price**. Estimate read counts, bytes retrieved, overwrite frequency, and potential reverse tier transitions. Pricing varies by region, redundancy, account type, and date, so use the **Azure Pricing Calculator** and real usage metrics when budgeting.

Metrics to track:

- Total Blob capacity by container, tier, and count of current vs. previous versions.
- List/read/write/delete operation counts, and rates of `403`, `404`, `409`, `412`, and `5xx` errors.
- Archived blob count, pending rehydration jobs, and rehydration completion times.
- Costs broken down by tier, retrieval, early deletion, and egress volume.
- Orphan blob counts caused by failed DB writes or abandoned uploads.
- Restore success rate and real RTO during restore drills.

## 13. Integration Testing and Common Pitfalls

### 13.1. Testing with Azurite and Real Azure

**Azurite** is useful for exercising basic Blob APIs locally. However, it **does not fully emulate** all behaviors of versioning, lifecycle management, Archive/rehydration, IAM managed identity, firewalls/private endpoints, or real billing. Therefore, split testing into two layers:

- **Local/unit/integration tests:** verify metadata logic, blob naming, upload/download, ETag conditions, and standard API error handling using Azurite/SDK.
- **Azure integration tests:** use a dedicated test account to validate versioning, soft delete, tiers, lifecycle policies, rehydration, data-plane RBAC, private endpoints, and background policy execution.

Never test deletion policies on a production storage account. Use isolated prefixes/containers, non-sensitive data, short lifecycle intervals for experiments (where supported), and safe resource cleanup.

### 13.2. Test Matrix

| Case | What to Verify |
|---|---|
| Attach new metadata | Properties return exact key-values; no sensitive data leaked |
| Two workers update metadata concurrently | One receives 412 when ETag changes; merge preserves prior keys |
| Update HTTP headers | Content and headers match post-update; aware of impact on ETag and sibling headers |
| Upload/overwrite with versioning enabled | Previous version is retrievable/restorable via version ID |
| Accidental delete with soft delete enabled | Recoverable within the configured retention window |
| Cool/Cold transition age reached | Tier transitions when lifecycle runs; do not assert exact minute-level timing |
| Transitioned to Archive | Direct download blocked; app surfaces appropriate restore state |
| Request to read an Archive blob | Rehydrates via workflow and updates status once online |
| Lifecycle deletes versions/snapshots | Only matching resources affected; retention and holds are respected |
| Under-privileged principal | Cannot modify metadata/tier/delete when RBAC disallows |
| Policy targets wrong prefix | Caught in testing prior to deploy with no unintended data loss |
| DB fails after upload | Orphan blob reconciliation and safe keep/delete rules apply |

### 13.3. Diagnostic Error Table

| Symptom | Possible Cause | Remediation |
|---|---|---|
| `403 Forbidden` | Missing RBAC, expired SAS, firewall/Shared Key policy | Check principal, role/scope, credentials, networking |
| `404 Not Found` | Wrong account/container/blob name, or only previous versions remain | Check resource, version list, soft delete, current state |
| `412 Precondition Failed` | ETag changed due to conflicting metadata/HTTP property update | Reload, merge per business rules, retry with cap |
| Old metadata disappeared | `setMetadata` overwrote the whole map | Fetch/merge completely and use `If-Match` |
| Cannot download Archive blob | Blob is offline, rehydration incomplete | Trigger job, track status, return result when online |
| Sudden cost spike | Many versions/snapshots, wrong tier, retrieval and early deletion fees | Break down by tier/operation, tune policy after analysis |
| Cannot delete blob despite Contributor | Immutable policy, legal hold, lease, or other restriction | Inspect policies/leases and storage operation preconditions |
| Lifecycle doesn't transition immediately | Background engine, threshold not met, unsupported account, or conflicting rule | Inspect rules, prefix/tags, modified time, tier state, logs, and service limits |

## 14. Practice Scenarios and Self-Check Questions

**Scenario A — Contract requiring 5-year retention:** Documents are read constantly during the first 30 days, then only a few times per year. Design prefixes/tags and a Hot → Cool/Cold → Archive path while ensuring no deletion before 5 years and supporting on-demand restores.

**Scenario B — Two jobs updating metadata:** An OCR job writes `ocrStatus=READY`, and a classification job writes `documentType=contract`. Both read the same old ETag. Use `If-Match` to avoid dropping either field and describe how to retry/merge on 412.

**Scenario C — Accidental PDF overwrite:** Versioning is enabled; current was corrupted, while the previous version is intact. Design a flow to pick the version ID, verify restore authorization, copy content to a new current version, and record an audit log.

**Scenario D — Downloading an Archive file:** A user urgently needs a 6-year-old document currently in Archive. Explain why the endpoint cannot stream content immediately, how to model `PENDING_REHYDRATION`, and how to notify the user once restored.

**Scenario E — Multi-cloud:** Compare Azure Blob metadata/index tags/lifecycle with **Amazon S3 object metadata, object tags, versioning, storage classes** and **Google Cloud Storage custom metadata, object generations, storage classes, lifecycle rules**. Focus on **principles**; API names, retention policies, storage classes, and condition mechanisms vary across providers.

### Self-Check

1. **Does metadata replace a database for business queries?** No. Metadata describes objects; a database is still required for relationships, ownership, permissions, and complex queries.
2. **Does `setMetadata` add one key while keeping all previous keys?** Not by default; you must merge and write the full map, using ETag to prevent lost updates.
3. **Is an ETag the same as a version ID or SHA-256?** No. ETag handles state conditions, version ID references a specific version, and SHA-256 verifies raw bytes.
4. **Does versioning make every deletion recoverable forever?** No. Policies, admin permissions, retention windows, and feature compatibility still govern recovery.
5. **Can an Archive blob be read immediately like Hot?** No. Archive is offline and normally requires asynchronous rehydration.
6. **Why do early deletion fees exist?** Cool/Cold/Archive tiers typically carry minimum retention durations; moving out or deleting early can incur extra charges.
7. **Does lifecycle execute at exactly 00:00 on day 90?** No. It is a background mechanism, so design for latency and monitor state.
8. **Does a lifecycle policy replace immutable retention?** No. Lifecycle automates conditional transitions/deletes; immutability enforces tamper/delete restrictions when legally or operationally required.
9. **Is enabling Blob Data Contributor enough to ensure web users only view their own documents?** No. The backend must check owner/tenant and only issue SAS/streams when authorized.

## 15. Summary

In Azure Blob Storage, **properties and metadata** describe objects, **index tags** support label-based filtering, **ETags** guard conditional updates, and **versioning/snapshots/soft delete** support recovery. **Hot/Cool/Cold/Archive** optimize different access patterns, and **lifecycle management** automates policy-driven tier transitions or deletions. Each capability has constraints and costs; design around **retention mandates, retrieval SLAs, access permissions, recovery plans, and real usage patterns**.

In Spring Boot, use Spring Cloud Azure and the Azure Storage SDK to read properties, update metadata with `If-Match`, and adjust tiers through authorized services. When moving to AWS S3 or Google Cloud Storage, object/version/storage-class concepts are similar, yet **IAM, APIs, lifecycles, and billing constraints differ** and must be verified per provider.

### Official References

- [Microsoft Learn — Set and retrieve properties and metadata for blobs](https://learn.microsoft.com/azure/storage/blobs/storage-blob-properties-metadata)
- [Microsoft Learn — Manage and find Azure Blob data with blob index tags](https://learn.microsoft.com/azure/storage/blobs/storage-manage-find-blobs)
- [Microsoft Learn — Blob versioning](https://learn.microsoft.com/azure/storage/blobs/versioning-overview)
- [Microsoft Learn — Soft delete for blobs](https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview)
- [Microsoft Learn — Azure Blob Storage access tiers](https://learn.microsoft.com/azure/storage/blobs/access-tiers-overview)
- [Microsoft Learn — Rehydrate an archived blob](https://learn.microsoft.com/azure/storage/blobs/archive-rehydrate-overview)
- [Microsoft Learn — Lifecycle management policies](https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-overview)
- [Microsoft Learn — Azure Blob Storage client library for Java](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)

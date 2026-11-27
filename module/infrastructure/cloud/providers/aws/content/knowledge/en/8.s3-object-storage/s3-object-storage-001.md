# S3 Buckets, Objects, Keys, and Consistency Model

> **Chapter:** S3 Object Storage  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore AWS services from Region/AZ infrastructure, IAM, and VPC to compute, storage, data, integration, and serverless; practice selecting solutions that are secure, observable, resilient, and cost-appropriate.

Amazon Simple Storage Service (**Amazon S3**) is an **object storage** service. Instead of creating a disk volume and managing an operating system's directory structure, an application stores an **object** in a **bucket** and accesses it via a **key** using APIs. This model is well-suited for product images, documents, backups, logs, analytics data, and static files that need to scale on demand.

To build applications correctly, learners need to understand two sets of concepts: the **data model** (`bucket → object → key`) and the **consistency model** (which state a read or list operation observes right after a write or delete). In modern S3, writing an object successfully and reading it back provides **strong read-after-write consistency**; however, that does not mean every operation involving multiple objects, caches, or multiple Regions behaves as a synchronous transaction.

Examples in this lesson primarily apply to **general purpose buckets**. S3 also offers **directory buckets** with their own structure, naming rules, placement model, and specific capabilities; these are contrasted in section 4. All bucket names, accounts, and keys in the examples are illustrative only and are not pre-existing resources in the learner's AWS account.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a **bucket**, **object**, **object key**, **prefix**, **metadata**, **tag**, and **version ID**.
2. Explain the flat namespace of a general purpose bucket; understand why paths containing `/` are not inherently real directories.
3. Choose and name a bucket, design object keys for an application, and identify the implications of bucket-level vs. object-level IAM permissions.
4. Accurately describe **strong consistency** for `PUT`, `GET`, `HEAD`, `DELETE`, and `LIST` when operating on objects.
5. Recognize the risks of **concurrent writes to the same key**, multi-key updates, enabling versioning, reading through a CDN, and cross-Region replication.
6. Perform basic S3 operations using the AWS CLI, propose strategies to prevent overwrites, and verify correctness in a test environment.

## 2. How Does S3 Differ from Disk Volumes and File Systems?

When using block storage such as **Amazon EBS**, the operating system sees a block device; you typically need to format a file system, mount it, and manage files. When using **Amazon EFS**, applications see a file system using an appropriate protocol with directory semantics. With **Amazon S3**, objects are stored and retrieved over HTTP/API or integrated tools.

| Need | Storage Type Typically Considered | Why |
| --- | --- | --- |
| Operating system disk/volume for EC2 | **EBS** | Block-level access for EC2 |
| Shared file system requiring a directory model and NFS protocol | **EFS** | Multiple machines share the same file system using NFS semantics |
| Images, videos, downloadable files, logs, backups, data lakes | **S3** | Object API, scalable capacity, and key-based retrieval |

**Do not equate S3 with a POSIX file system**: general purpose buckets do not support operations like `rename()`, file locking, appending, or updating a few bytes in place like a standard disk. "Renaming a file" typically requires **copying the object to a new key and then deleting the old key**; this is not an atomic transaction across two keys. Some applications use an integration layer to *mount* S3, but doing so does not turn S3 into a full POSIX file system.

## 3. Three Core Concepts: Bucket, Object, and Key

~~~mermaid
flowchart TB
    B["General purpose bucket: example-learning-assets-2026"]
    B --> O1["Object 1"]
    B --> O2["Object 2"]
    B --> O3["Object 3"]
    O1 --> K1["key = images/products/sku-123/front.webp"]
    O2 --> K2["key = reports/2026/11/sales.csv"]
    O3 --> K3["key = reports/2026/11/summary.json"]
    O1 --> M1["Body + metadata + tags + optional version ID"]
    O2 --> M2["Body + metadata + tags + optional version ID"]
    O3 --> M3["Body + metadata + tags + optional version ID"]
~~~

The diagram illustrates the logical structure. Strings like `images/`, `products/`, and `reports/` are merely parts of the key and can be used as a **prefix**.

### 3.1. Bucket

A **bucket** is a container for objects and the place where many important settings are applied: Region/storage location, access permissions, versioning, lifecycle, encryption, and logging. For a general purpose bucket, the bucket name must be **unique within the applicable AWS partition**, so a simple name may already be taken by another account.

Example:

~~~text
Bucket name: example-learning-assets-2026
Region:      ap-southeast-1
Purpose:     Product images and reports for the sample application
~~~

Key points to remember:

- A bucket name is distinct from an object name. The bucket is the container, and an object is identified by its **key inside the bucket**.
- A general purpose bucket's Region is chosen at creation time; there is no in-place command to "change Region" for an active bucket. Moving to another Region usually requires creating a destination bucket and migrating/copying the data.
- A bucket does not automatically become public just because its name resembles a website domain. Access depends on IAM, bucket policies, S3 Block Public Access, Object Ownership, and other settings.
- **A bucket name is not secret information**, and you should not embed sensitive data in the name.
- In practice, check the **current naming rules**; names have reserved prefixes/suffixes for S3 features and cannot be chosen arbitrarily.
- Some bucket-level settings, such as enabling versioning for the first time, have their own propagation delay; do not assume all bucket administrative operations share the same consistency guarantees as object GET/PUT.

A bucket can hold many objects. **S3 does not require you to pre-allocate total capacity** for the entire bucket; however, there are limits per API, object, request, and account quota depending on the scenario. Check the service documentation before designing large-scale uploads.

### 3.2. Object

An **object** consists of **data content** (*body*) and **associated descriptive metadata/attributes**, stored under a key in a bucket. When versioning is enabled, a key can be associated with multiple versions, each having its own **version ID**.

| Component | Example | Role |
| --- | --- | --- |
| **Object key** | `images/sku-123/front.webp` | Unique logical address within the bucket for the current version |
| **Body** | The bytes of a WebP image | Content uploaded by the application |
| **Content-Type** | `image/webp` | Tells clients the declared media type |
| **System metadata** | Size, last modified time, ETag | Information managed by S3 and the API |
| **User-defined metadata** | `x-amz-meta-source: catalog` | Information declared by the application when writing/copying the object |
| **Object tags** | `Environment=prod`, `Team=catalog` | Classification for IAM, lifecycle, and management |
| **Storage class** | `STANDARD`, `STANDARD_IA`, ... | Storage/retrieval optimization tier based on access needs |
| **Encryption** | SSE-S3 or an appropriate encryption method | Protects data at rest, managing keys according to policy |
| **Version ID** | Value returned by S3 when versioning is enabled | Targets a specific version of a key |

**Metadata is not an object tag**. Metadata is typically set when uploading the object; changing user-defined metadata may require **copying the object with the new metadata set**. Tags are managed through a dedicated tagging API when supported by the service/bucket type. Both require appropriate IAM permissions and have size/count limits.

**ETag is not always the MD5 of the entire body**. Especially with multipart uploads and certain encryption methods, do not rely on ETag as a general-purpose MD5 checksum. When an application needs integrity verification, use S3-supported checksums and verify the upload workflow.

### 3.3. Object Key

A **key** is the name of an object **inside a bucket**; general purpose buckets allow keys up to **1,024 UTF-8 bytes** long. Keys are case-sensitive:

~~~text
images/products/sku-123/front.webp
images/products/sku-123/FRONT.webp
~~~

The two lines above are **two different keys**. Without versioning enabled, writing a new object to the **same key** normally replaces the current content; writing to a different key creates a different object.

An easy-to-read logical identifier:

~~~text
s3://example-learning-assets-2026/images/products/sku-123/front.webp
└────────────────── bucket ──────────────────┘└────── object key ────────┘
~~~

`s3://...` is the AWS CLI/SDK notation, **not an HTTPS URL that a browser can load directly**. HTTPS access requires the appropriate endpoint, valid permissions, or an active **presigned URL**; a key may also need to be properly URL-encoded when placed in an HTTP path.

## 4. Prefixes, `/` Characters, and "Folders" in S3

In a **general purpose bucket**, the key space is **flat** (*flat namespace*). The S3 Console UI typically displays keys containing `/` as folders to make browsing easier for users.

Example keys:

~~~text
images/products/sku-123/front.webp
images/products/sku-123/back.webp
images/products/sku-456/front.webp
reports/2026/11/sales.csv
reports/2026/12/sales.csv
readme.txt
~~~

When you want to look "inside the `images/products/sku-123/` folder," the application is actually filtering keys by a **prefix**:

~~~text
Prefix = images/products/sku-123/
Result = two keys .../front.webp and .../back.webp
~~~

The `/` **delimiter** allows the `ListObjectsV2` API to group key strings into `CommonPrefixes`, creating a folder-browsing experience. However, in a general purpose bucket:

- You do not need to create a "parent folder" before PUTting an object whose key contains `/`.
- An object with key `images/products/` and an empty body may exist (often created by the Console as a *folder marker*), but this **does not turn a prefix into a POSIX directory**.
- Renaming `reports/2026/` does not automatically rename all objects like renaming a directory on disk; you must process each object or group of objects via a copy/delete workflow or compatible tool.
- Characters such as spaces, `+`, Unicode, `./`, `../`, or trailing `/` can cause confusion with CLIs, URL parsers, browsers, and integration tools. Prefer simple, consistent key naming conventions.

### 4.1. Key Naming Conventions for Applications

An easy-to-manage structure for an e-commerce system:

~~~text
assets/products/<product-id>/<image-id>.webp
exports/orders/year=2026/month=11/day=20/<export-id>.parquet
logs/service=checkout/year=2026/month=11/day=20/<request-batch>.json.gz
backups/db/<backup-timestamp>/<filename>
~~~

In a real application, replace `<...>` segments with safely generated or validated values. You can use UUIDs/ULIDs to avoid key collisions, time-based partitioning for easier querying, and separate **user-supplied input** from internal conventions.

**Do not use keys to store sensitive data.** Object keys can appear in logs, URLs, metrics, and error messages. Never put access tokens, passwords, personal ID numbers, or application secrets into a key.

### 4.2. General Purpose Buckets vs. Directory Buckets

S3 currently provides multiple bucket types. This lesson focuses on **general purpose buckets**, where prefixes are purely a logical key organization mechanism. **Directory buckets** have a true hierarchical structure based on `/`, used with appropriate storage classes/features such as **S3 Express One Zone** in a selected Zone; their bucket naming rules, endpoints, APIs, and supported features differ from general purpose buckets.

| Aspect | General Purpose Bucket | Directory Bucket |
| --- | --- | --- |
| Key structure | Flat namespace; `/` is used as prefix/delimiter | Hierarchical directory-based namespace |
| Location | Select a Region when creating the bucket | Tied to an eligible Zone depending on the directory bucket type |
| Naming | Unique within the applicable AWS partition | Has a Zone ID suffix of the form `--zone-id--x-s3` |
| Primary use cases | Images, general-purpose storage, backups, data lakes | Workloads requiring low-latency object access close to compute |
| Features | Wide range of storage classes, versioning, and standard S3 features | Some features/APIs/limits differ and must be checked separately |

**Do not blindly copy all commands in this lesson to a directory bucket** without checking the S3 Express / Directory Buckets documentation. For example, certain versioning behaviors, endpoints, and listing semantics differ.

## 5. Bucket/Object Names and Addresses Across APIs

Three common forms:

| Representation | Example | Where Used |
| --- | --- | --- |
| **S3 URI** | `s3://example-learning-assets-2026/reports/2026/11/sales.csv` | AWS CLI, some integrations |
| **Bucket ARN** | `arn:aws:s3:::example-learning-assets-2026` | IAM `s3:ListBucket` and certain bucket-level permissions |
| **Object ARN** | `arn:aws:s3:::example-learning-assets-2026/reports/*` | IAM `s3:GetObject`, `s3:PutObject`, etc. |

An S3 general purpose bucket ARN does not include a Region or account ID in those ARN fields as many EC2 ARNs do. That does **not** mean objects exist globally or that IAM does not enforce account-level access control.

With AWS SDKs, you typically pass **bucket** and **key** separately:

~~~javascript
// S3 API pseudocode illustrating request structure
const request = {
  Bucket: "example-learning-assets-2026",
  Key: "reports/2026/11/sales.csv"
};
~~~

Bucket policies typically apply to bucket or object ARNs, while application code performs PUT/GET with the exact bucket name and key. Do not pass an `s3://...` string as `Key`, because the `s3://bucket/` prefix is not part of the key.

## 6. S3 Consistency Model: Strong Read-After-Write

### 6.1. When a PUT Succeeds

For objects in S3, **strong read-after-write consistency** means: after a `PUT` call succeeds and the client receives a success response, subsequent **GET** or **LIST** calls initiated afterward will see the new object/data. This applies to both **new objects** and **overwrites of existing objects**; successful delete (`DELETE`) requests are also strongly consistent.

For current objects in a bucket, the following table describes the expected result assuming no other intervening writes occur:

| Successfully Completed Action | Subsequent GET/HEAD | Subsequent LIST |
| --- | --- | --- |
| **PUT new key** `a.txt` | Sees new content/metadata | Includes `a.txt` |
| **PUT overwrite** `a.txt` | Sees new current version | Key `a.txt` still appears |
| **DELETE** key `a.txt` | Does not return the deleted current object | `a.txt` no longer in current object listing |
| **PUT new metadata/object on same key** | Sees new state of current object | Sees appropriate key |

S3 also provides strong consistency for many supported metadata, object tag, and ACL read operations. Distinguish this from changes to **bucket-level configurations** (such as certain versioning or policy settings) and external systems, which may have their own propagation delays.

### 6.2. Timeline of PUT → GET → LIST

~~~mermaid
sequenceDiagram
    participant Writer as File Writer Service
    participant S3 as Amazon S3
    participant Reader as File Reader Service
    Writer->>S3: PUT reports/2026/11/sales.csv = V1
    S3-->>Writer: 200 OK / success
    Reader->>S3: GET same key (after success response)
    S3-->>Reader: Body V1
    Reader->>S3: LIST prefix reports/2026/11/
    S3-->>Reader: Includes sales.csv
~~~

If a PUT succeeds at time `t1`, GET/LIST requests **initiated after `t1`** can observe the new state without requiring clients to wait "a few seconds for S3 to sync" as described under older eventual consistency explanations.

### 6.3. Overwrites Do Not Produce Half-Old, Half-New States

When S3 processes an update to **a single key**, the operation is **atomic at the object/key level**: for a GET concurrent with an overwrite, the client may receive **either the full old body or the full new body**, never a corrupted file mixing half old bytes and half new bytes from S3.

Example:

~~~text
Before PUT: key = config/app.json, body = V1
New PUT:    key = config/app.json, body = V2

GET concurrent with PUT: may see V1 or V2
GET initiated after PUT success response: sees V2,
assuming no newer write/delete occurred.
~~~

This is **single-object atomicity**, not a multi-object transaction.

### 6.4. DELETE and GET: IAM Nuances

After deleting the current object succeeds, S3 no longer returns the current body. However, the **HTTP status** the client observes also depends on permissions:

- With appropriate `s3:ListBucket` permission, a GET request for a non-existent key typically receives `404 NoSuchKey`.
- If the principal lacks `s3:ListBucket` permission, a GET request for a non-existent key may receive **`403 AccessDenied`** instead of 404.

Therefore, **403 does not prove an object exists**, and 404 does not automatically prove the application configuration is correct. When debugging, inspect IAM, bucket policy, encryption, key, versioning, and request context.

## 7. What S3 Strong Consistency Does **Not** Guarantee

Strong consistency on S3 object operations does not mean every system layered on top immediately returns fresh data.

### 7.1. No Atomic Multi-Key Transactions

Suppose a report export job writes:

~~~text
reports/2026-11-20/part-0001.csv
reports/2026-11-20/part-0002.csv
reports/2026-11-20/manifest.json
~~~

The two `part` files and `manifest.json` are **three separate objects**. If the application fails halfway through writing the second file, a client calling LIST may observe an intermediate state (for example, only `part-0001.csv`). S3 does not guarantee **all-or-nothing** across the three PUTs.

**Recommended design pattern:** write data parts under immutable keys, verify they are complete, and **lastly** write a manifest or `_SUCCESS` marker. Clients read the manifest to know which dataset is ready. When multi-record transactional consistency is required, consider pairing S3 with a transactional datastore such as DynamoDB or a relational database.

### 7.2. Does Not Automatically Resolve Concurrent Write Conflicts on the Same Key

Two clients concurrently PUTting to the same key can overwrite each other. S3 handles consistency at the key level, but the application needs a mechanism to **prevent lost updates** if both clients have write permissions.

### 7.3. Does Not Keep CDN Caches Automatically Fresh

For example, suppose CloudFront has cached `images/sku-123/front.webp` and its TTL has not expired. If the application PUTs a new image to the **same key** in S3, a client calling GET directly on S3 after the PUT succeeds will see the new body, while end users going through CloudFront **may still receive the stale cached copy** until the cache expires or is invalidated by design.

**Recommendation:** for static assets, use content-versioned keys such as `front.a3d91c.webp` and update the references on the page; for resources that must keep the same URL, design appropriate Cache-Control/TTL headers and invalidation workflows.

### 7.4. Does Not Make Cross-Region Replication Instantaneously Synchronous

**S3 Replication** (such as Cross-Region Replication) typically runs **asynchronously**. A GET on the source bucket sees new data immediately after a successful PUT, while the destination bucket in another Region may not yet have received the replica. You must monitor replication status/metrics and design an appropriate **RPO and failover procedure**.

Similarly, S3 Event Notifications or data pipelines through SQS/Lambda/EventBridge have their own delivery mechanisms, latency, and potential for duplicates. **S3 strong consistency does not mean events always arrive exactly once and in global order**; consumers must be designed to be idempotent.

### 7.5. Network Errors Do Not Mean the PUT Failed

A client can send a PUT that succeeds in S3 yet **fail to receive the response** due to a network timeout. In that case, you cannot conclude the object was not stored. Rather than retrying blindly, use a key/idempotency strategy, `HEAD`, or conditional write conditions to decide the next step.

## 8. Concurrent Writes, Conditional Writes, and ETag

### 8.1. What Is a Lost Update?

Two services read the same state and then both write back to the same key:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant S as S3 (object config.json)
    participant B as Writer B
    A->>S: GET config.json = V1
    B->>S: GET config.json = V1
    A->>S: PUT config.json = V2A
    S-->>A: Success
    B->>S: PUT config.json = V2B
    S-->>B: Success
    Note over A,B: B can overwrite A's change
~~~

After B's PUT succeeds and with no other writes, GET will return V2B. S3 **does not automatically lock an object to coordinate Writer A and Writer B**. Seeing the latest data and coordinating multiple writers are two distinct problems.

### 8.2. `If-None-Match: *`: Write Only If the Key Has No Current Object

A conditional PUT with the `If-None-Match: *` header instructs S3 to create the object only if no current object exists at that key. If the key already has a current object, S3 returns `412 Precondition Failed`. This is useful when an application wants to **prevent overwrites** or enforce non-colliding keys.

AWS CLI example (on CLI versions supporting this parameter, with an existing bucket):

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key exports/job-123/result.csv \
  --body ./result.csv \
  --if-none-match "*"
~~~

During competing writes or deletes, some requests may receive **`409 ConditionalRequestConflict`**. Retry logic should be based on the actual error code and API behavior; do not automatically treat every 409 as a permanent failure.

**When versioning is enabled:** if the current version is a **delete marker**, an `If-None-Match: *` request can succeed because there is no current object version. Thus, this condition **does not guarantee the key has never existed in history**.

### 8.3. `If-Match`: Write Only If the Object Matches the Previously Read State

An application calls `HEAD`/`GET` to obtain the **current ETag**, then updates only if the ETag has not changed:

~~~text
HEAD  config/app.json → ETag = "etag-v1"
PUT   config/app.json with If-Match: "etag-v1"

If current ETag still matches: write succeeds
If ETag differs: 412 Precondition Failed
~~~

This is a form of **optimistic concurrency control**: it prevents silently overwriting changes when another writer modified the object. However, ETag is an object-state matcher, not a guaranteed MD5 checksum across all upload methods. The application still needs to handle contention, deletion, timeouts, and controlled retries.

### 8.4. Choosing the Right Update Pattern

| Scenario | Strategy to Consider |
| --- | --- |
| Exporting one file per run without overwriting | Keys containing unique IDs; `If-None-Match: *` |
| Multiple editors updating the same config object | `HEAD/GET` to fetch ETag, `If-Match` on PUT, handle conflicts |
| Need to restore older revisions | S3 Versioning and recovery procedures |
| Writing multiple objects as one "release" | Write immutable objects first, update manifest last |
| Financial/order workflows requiring multi-record atomicity | Use a transactional datastore; use S3 only for appropriate files/outputs |
| Must prevent deletion/modification during a retention period | Consider S3 Object Lock and appropriate administrative permissions |

**S3 Object Lock** is a retention/object-locking feature under supported modes, **not a coordination lock for writers**. Do not infer from the name "Object Lock" that S3 provides a mutex for concurrent PUTs to the same key.

## 9. Versioning: Multiple Versions Under a Single Key

**S3 Versioning** is a bucket-level feature that retains object versions. When enabled:

- A PUT to an existing key creates a **new version**; the previous version becomes a *noncurrent version* instead of being immediately overwritten and lost.
- A normal GET retrieves the **current version** of the key.
- A GET specifying a valid **version ID** can read an older version if the principal has permission and the object is still stored.
- A DELETE **without specifying a version ID** typically inserts a **delete marker** that becomes the current version. Prior objects can still remain in version history.
- To **permanently delete a version**, you must use the version-specific delete operation and permissions; this differs from a normal DELETE.

~~~mermaid
flowchart LR
    V1["PUT key=a.txt, body=V1"] --> V2["PUT same key, body=V2"]
    V2 --> D["DELETE without version ID"]
    D --> M["Current = delete marker"]
    M --> OLD["V1, V2 can remain as noncurrent versions"]
~~~

**Be careful saying "DELETE permanently deletes"**: in a versioning-enabled bucket, a DELETE without a version ID causes a GET on the current object to fail as non-existent (depending on permissions), yet older versions can still be recovered if retained.

For production systems:

- Versioning reduces the risk of accidental overwrites or deletes, but **does not replace backups, least-privilege permissions, and restore drills**.
- Each version consumes storage in its respective storage class and incurs cost; use **Lifecycle Rules** to manage noncurrent versions and retention periods as required.
- After enabling versioning for the first time, AWS notes there is a propagation delay; allow the change to propagate before relying on versioning in a sensitive workflow.
- Versioning has states such as **Enabled** and **Suspended**; understand the behavior of `null version` and delete markers before changing states.

Read-only CLI example to list versions (requires `s3:ListBucketVersions`):

~~~bash
aws s3api list-object-versions \
  --bucket example-learning-assets-2026 \
  --prefix reports/2026/ \
  --query "{Versions:Versions[].{Key:Key,Version:VersionId,Latest:IsLatest},DeleteMarkers:DeleteMarkers[].{Key:Key,Version:VersionId,Latest:IsLatest}}" \
  --output json
~~~

## 10. LIST and Pagination Rules

`ListObjectsV2` returns a list of current objects matching the filter criteria. A single request has a cap on how many keys it returns; for large lists, you must **paginate** using a continuation token or an AWS SDK/CLI paginator.

Example listing objects with prefix `reports/2026/11/`:

~~~bash
aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix reports/2026/11/ \
  --query "Contents[].{Key:Key,Size:Size,LastModified:LastModified}" \
  --output table
~~~

Example grouping "subfolders" using a delimiter:

~~~bash
aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix reports/ \
  --delimiter "/" \
  --query "{Files:Contents[].Key,Folders:CommonPrefixes[].Prefix}" \
  --output json
~~~

**Key distinctions:**

- `Prefix` is a **key-string prefix filter**, not a real directory in a general purpose bucket.
- `Delimiter` groups keys into `CommonPrefixes`; those prefixes are not objects.
- For general purpose buckets, LIST results are returned in lexicographical order by key under the applicable API semantics; **directory buckets** have different ordering rules and cannot be assumed identical.
- **Each LIST page is evaluated at the time of its individual request**. If an application adds or deletes keys while scanning across multiple pages, do not treat the combined result of all pages as an immutable **snapshot transaction**.
- Listing does not guarantee that the client has `GetObject` permission for every key visible in the list; IAM defines separate actions for buckets and objects.

### 10.1. A Common Logic Bug

Suppose an ETL job processes all keys with prefix `incoming/`. Another process is still actively uploading new data there. A paginated LIST loop can read a set of keys that changes mid-run, leading to missed files or duplicate processing when combined with retries or key changes.

**Design approach:** use immutable keys, write a marker/manifest when a batch finishes, or use queues/events with idempotent processing state. Strong consistency on individual S3 requests **does not replace an application-level mechanism for determining "a batch is closed"**.

## 11. Multipart Upload and Consistency

For large objects, S3 supports **multipart upload**: the application initiates an upload, sends parts, and finishes with `CompleteMultipartUpload`. A key only becomes a **current object** after completion succeeds; uploading a few parts does not turn them into a complete object readable by key via GET.

~~~mermaid
flowchart LR
    START["CreateMultipartUpload"] --> P1["UploadPart 1"]
    START --> P2["UploadPart 2"]
    START --> P3["UploadPart N"]
    P1 --> COMPLETE["CompleteMultipartUpload"]
    P2 --> COMPLETE
    P3 --> COMPLETE
    COMPLETE --> VISIBLE["Current object visible to GET/LIST"]
~~~

Once completion succeeds, strong consistency applies to the current object. If an error occurs midway, the multipart upload may leave incomplete parts behind and **incur storage charges**; abort unused uploads or configure a lifecycle rule to clean up incomplete multipart uploads.

**ETag note:** multipart uploads typically produce an ETag that is not equal to the MD5 of the complete object. Use API-supported checksums to verify integrity.

## 12. IAM and Security Tied to Buckets and Keys

S3 is typically deployed following the principle of **private by default, least privilege**. AWS enforces permissions via IAM identities, bucket policies, relevant governance/guardrail policies, and public access settings. Never rely on hard-to-guess object keys as a security control in place of authorization.

### 12.1. Bucket and Object Permissions Are Two Resource Levels

| Operation | IAM Action | Typical ARN |
| --- | --- | --- |
| List keys in bucket | `s3:ListBucket` | `arn:aws:s3:::example-learning-assets-2026` |
| Read object body | `s3:GetObject` | `arn:aws:s3:::example-learning-assets-2026/exports/*` |
| Write object | `s3:PutObject` | `arn:aws:s3:::example-learning-assets-2026/uploads/*` |
| Delete current object | `s3:DeleteObject` | Object ARN |
| Read specific version | `s3:GetObjectVersion` | Object ARN, appropriate permissions |
| List versions | `s3:ListBucketVersions` | Bucket ARN |

Example identity-based policy for an ETL role **allowed to list and read** files under `reports/`, with no Allow for upload or delete:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListReportPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::example-learning-assets-2026",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["reports/", "reports/*"]
        }
      }
    },
    {
      "Sid": "ReadReportObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-learning-assets-2026/reports/*"
    }
  ]
}
~~~

**Explanation:**

1. `s3:ListBucket` must use the **bucket ARN**, and can include `s3:prefix` to restrict listing to only the required prefix.
2. `s3:GetObject` uses the **object ARN**, with a wildcard limiting the prefix.
3. There is no Allow for `PutObject`, `DeleteObject`, or `GetObject` outside the specified prefix.
4. This policy does not account for additional restrictions from AWS Organizations/SCPs, permissions boundaries, bucket policies, KMS key policies, or real-world environment conditions.

### 12.2. Encryption, Ownership, and Public Access

- S3 encrypts new objects at rest by default using SSE-S3; if using **SSE-KMS**, applications must also have appropriate KMS permissions and manage key policies.
- **S3 Block Public Access** should be configured at the appropriate scope to prevent accidental unwanted public exposure.
- **Object Ownership – Bucket owner enforced** (when applied) simplifies ownership control and disables ACLs in supported scenarios; prefer IAM and bucket policies over individual ACLs unless there is a specific requirement.
- For files served through **CloudFront**, you can keep the S3 bucket private and use **Origin Access Control (OAC)** so CloudFront accesses the origin according to policy.
- A presigned URL grants capability to perform a specific request within a time window/condition using the signing principal's permissions; it does not make an object permanently public, but **the URL acts as a bearer token** and must be kept confidential while valid.
- A bucket or object can still be blocked by VPC endpoint policies, IP/condition checks, Block Public Access, or an explicit Deny even if an identity policy has an Allow.

### 12.3. Aligning Keys and Data with Recovery Needs

Product images, logs, and backups do not share the same requirements:

| Data | Key Requirements | Considerations |
| --- | --- | --- |
| Public images/static files | Fast loading and effective caching | Private S3 origin + CloudFront, content-versioned keys |
| Sensitive reports | Readable only by authorized roles, edit history | IAM/prefix, encryption, versioning, auditing |
| Backups | Recoverability from accidental deletion or ransomware | Versioning, Object Lock if appropriate, replication/backup, restore testing |
| System logs | High write frequency, compliance retention, later querying | Time-partitioned prefixes, lifecycle, separate write-only permissions and retention |
| Data lake | Many files, partitioned data, parallel ETL | Immutable keys, manifest/transaction layer, lifecycle, catalog |

S3 Standard stores data across multiple AWS-managed AZs within a Region. **Not all storage classes have the same AZ scope**; for example, One Zone classes store data in a single AZ. Choose a storage class based on latency, access frequency, recovery objectives, and actual pricing.

## 13. AWS CLI Hands-On: Observing Consistency

This lab uses **a dedicated general purpose bucket for lab exercises**. Commands can create/delete objects and incur request/storage charges; **do not run them against production buckets**. Only proceed when you have permission for lab data and have double-checked the bucket and key names. Commands assume the AWS CLI is installed and a Bash-like shell (Linux/macOS/WSL); PowerShell uses different variable syntax.

### 13.1. Preparation

1. Choose an existing lab bucket in the appropriate Region, or create a new bucket in a lab account following official guidelines.
2. Ensure you have the necessary permissions to read, list, write, and delete lab objects, plus bucket permissions if creating a bucket yourself.
3. Create local files `report-v1.txt` and `report-v2.txt`, ensuring they contain no real/sensitive data.
4. Verify your AWS identity before making changes.

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

In the examples below, replace `example-learning-assets-2026` with your managed lab bucket name and place the two prepared files in your current directory. These examples **do not create a bucket** and do not call `DeleteBucket`.

### 13.2. PUT a New Object

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --body ./report-v1.txt
~~~

Proceed only after the command returns successfully. Details such as ETag, version ID, or checksums in the response depend on bucket configuration and upload method.

### 13.3. GET and HEAD Immediately After PUT

~~~bash
aws s3api head-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --query "{Length:ContentLength,ETag:ETag,Modified:LastModified}" \
  --output json

aws s3api get-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  ./downloaded-report.txt
~~~

Compare `downloaded-report.txt` with `report-v1.txt` using the appropriate OS tool. When the PUT has completed successfully and no other writer intervened, GET will return body V1.

### 13.4. LIST Immediately After PUT

~~~bash
aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix lab/consistency/ \
  --query "Contents[].{Key:Key,Size:Size}" \
  --output table
~~~

The output must include the key `lab/consistency/report.txt` if the bucket, key, and permissions are correct and no other operation deleted or modified it in the meantime.

### 13.5. Overwrite and Read Back

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --body ./report-v2.txt

aws s3api get-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  ./downloaded-report-v2.txt
~~~

Once the V2 PUT succeeds and with no newer writes, the GET result is **V2**. If versioning is enabled on the bucket, V1 may still exist as a noncurrent version.

### 13.6. Test Overwrite Prevention

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --body ./report-v1.txt \
  --if-none-match "*"
~~~

If the key currently has an active object, this command is expected to fail with `412 Precondition Failed`. This is an **expected error in the test**, confirming that the conditional PUT blocked the overwrite.

### 13.7. Clean Up Lab Data

Delete **only the exact lab key** just created, after verifying the bucket and key:

~~~bash
aws s3api delete-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt

aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix lab/consistency/ \
  --output json
~~~

If versioning is enabled, the DELETE command may create a **delete marker**; previous versions still exist, incur storage charges, and require a separate procedure if you want to purge all history. **Do not run bulk delete commands or DeleteBucket** without first inspecting the full list of versions/objects and permissions in the lab environment.

## 14. Practical Scenarios: Product Images and Order Reports

### 14.1. Product Images

The product team wants to replace the image for SKU-123. There are two approaches:

**Approach A — overwrite the same key**

~~~text
PUT images/products/sku-123/front.webp  (new body)
Direct GET from S3 after PUT succeeds → new body
GET via CloudFront before cache expires → may still return old body
~~~

The advantage is keeping the URL stable. The downside is having to manage cache invalidation, and overwrites can cause data loss without versioning or conditional writes.

**Approach B — immutable content-versioned keys**

~~~text
PUT images/products/sku-123/front.20261120-a3d9.webp
GET new key from S3 → new body
Application updates catalog to point to the new key
~~~

Approach B makes caching cleaner and avoids overwrites; it requires a mechanism to clean up unused versions according to a retention policy.

### 14.2. Order Reports

A daily order export job may produce multiple data parts:

~~~text
exports/orders/date=2026-11-20/part-0001.parquet
exports/orders/date=2026-11-20/part-0002.parquet
exports/orders/date=2026-11-20/manifest.json
~~~

Workflow:

1. Workers create each part file with a distinct key, never overwriting completed files.
2. After all PUTs succeed, the service verifies all files/keys are present and writes `manifest.json` last.
3. Consumers only read valid manifests and then process the exact keys listed therein.
4. On retry, the job must distinguish completed files, failed files, and re-runnable batches; use a job ID and idempotency key.

This is an **application-layer guarantee pattern**, not a multi-object transaction provided natively by S3.

### 14.3. What Role Does S3 Fit in AWS Architecture?

~~~mermaid
flowchart TB
    USER["User"] --> APP["API running on EC2/ECS/Lambda"]
    APP -->|"PUT original image"| S3["S3 general purpose bucket"]
    APP --> DB["RDS/DynamoDB: business metadata"]
    S3 --> CF["CloudFront: object caching"]
    CF --> USER
    S3 -.->|"Event notification - asynchronous"| Q["SQS/EventBridge/Lambda"]
    Q --> WORKER["Process image, generate thumbnail"]
    WORKER -->|"PUT new thumbnail key"| S3
~~~

In this flow, the database typically holds business metadata such as product ID, owner, visibility permissions, and the corresponding **key/version**. S3 holds the image body. If events are redelivered or delayed, workers must be idempotent; when the catalog changes, ensure DB metadata does not point to an object that is not yet ready.

## 15. Common Misconceptions

| Claim | Accurate Understanding |
| --- | --- |
| "S3 is a disk with traditional folders." | General purpose buckets have a **flat key namespace**; `/` is a prefix convention. |
| "Bucket names can be duplicated across Regions." | For general purpose buckets, names must be unique within the relevant **AWS partition**. |
| "The key is the full `s3://bucket/file` string." | The key is only `file` or the relative path inside the bucket. |
| "After a PUT succeeds, you have to wait a few seconds before GET/LIST sees it." | S3 provides **strong read-after-write consistency** for supported object operations. |
| "Strong consistency means all GETs concurrent with a PUT see the new version." | A **concurrent** GET may see either the old or the new version, never a partially written object. |
| "Two PUTs to the same key automatically merge data." | Concurrent writes can overwrite each other; use conditional writes or versioning as needed. |
| "Writing 10 objects is a single transaction." | S3 does not have atomic multi-object transactions; applications must implement manifests or workflows. |
| "Renaming a folder is an atomic operation." | In general purpose buckets it typically requires copying/deleting multiple objects, with intermediate states. |
| "Versioning makes DELETE erase data completely from history." | DELETE normally creates a delete marker; noncurrent versions can still remain. |
| "ETag always equals MD5." | Not true for many upload/encryption types, especially multipart uploads. |
| "When S3 updates, CloudFront immediately returns the new version too." | Caches/CDNs have independent TTLs and invalidation policies. |
| "A replica in a second Region is immediately consistent with the source." | Replication has asynchronous lag; you must measure and design for RPO. |
| "Seeing a key in LIST is enough permission to GET its body." | `ListBucket` and `GetObject` are separate permissions. |
| "Because S3 is strongly consistent, events arrive strictly once and in order." | Notifications/queues have their own delivery models; consumers need idempotency. |

## 16. Self-Check

### Exercise 1 — Bucket or Key?

Look at the representation:

~~~text
s3://shop-media-2026/assets/products/sku-001/main.png
~~~

Identify the bucket, the key, and the `assets/products/` prefix.

**Hint:** the bucket is `shop-media-2026`; the key is `assets/products/sku-001/main.png`. The prefix `assets/products/` is a filter for keys starting with that string and does not require creating a physical directory in a general purpose bucket.

### Exercise 2 — Read After Write

Service A PUTs `orders/summary.json` = V2 and receives a success response. Service B initiates a GET for the same key from the same bucket, without caching and with no other writers. Does B see V1 or V2?

**Hint:** B receives V2 due to strong read-after-write consistency. If the GET happened **concurrently** with the PUT, the result could be either the complete V1 or complete V2.

### Exercise 3 — Two Writers

Workers A and B both read the ETag of `config/app.json`, and then both attempt to overwrite that key. Propose a way to prevent B from accidentally overwriting A's change.

**Hint:** use `If-Match` with the ETag that was read, and handle `412 Precondition Failed` by re-reading and resolving the conflict. If the same key is not required, use keys with unique identifiers and `If-None-Match: *`.

### Exercise 4 — Deleting an Object with Versioning

A bucket with versioning enabled contains V1, then V2 is PUT, and then DELETE is called without specifying a version ID. Why does GET on the current object return no body while the version history still has V1/V2?

**Hint:** DELETE creates a current **delete marker**. Noncurrent versions may still be stored; recovering requires handling the marker or reading/copying the appropriate version with permission.

### Exercise 5 — CDN Not Showing Update

An application PUTs a new image to S3 and sees the new image with a direct GET, yet the website still displays the old image through CloudFront. Has S3 lost strong consistency?

**Hint:** No. Check cache TTL, Cache-Control, object path, and invalidation; consider immutable keys containing a content version identifier.

### Exercise 6 — Safe Batch Design

A pipeline must export 200 CSV files and then signal "batch ready." Readers must only process the batch when all 200 files are present. Why shouldn't readers simply LIST the prefix and assume all data is there? Design the manifest, write conditions, and retry handling.

**Hint:** LIST does not indicate whether the upload process has finished. Write each part with an immutable key, verify counts/checksums, and write the manifest last (optionally using a conditional write); readers only process the exact set of files listed in the manifest.

## 17. Key Takeaways

A **bucket** is the container configured with location and permissions; an **object** is the data along with its associated attributes; a **key** is the identifier of an object within a bucket. For **general purpose buckets**, keys may contain `/` to simulate folders, but the namespace is fundamentally **flat**.

Amazon S3 now provides **strong read-after-write consistency** for new writes, overwrites, deletes, and object listings: after a success response, subsequent GET/LIST operations reflect the new state unless concurrent activity intervenes. Each object is an atomic unit; **there are no automatic multi-key transactions**. When designing real-world systems, you must incorporate appropriate mechanisms for concurrent writes, versioning, caching, replication, IAM, cost, and data recovery tailored to business requirements.

### Official AWS Documentation

- [What is Amazon S3? — Data consistency model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel) — strong read-after-write for PUT, DELETE, GET/LIST and multi-key update limits.
- [General purpose buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingBucket.html) — bucket concepts and general configuration.
- [Naming Amazon S3 objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html) — keys, prefixes, delimiters, lengths, and characters.
- [Listing object keys programmatically](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ListingKeysUsingAPIs.html) — `ListObjectsV2`, prefixes, and pagination.
- [Working with directory buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-buckets-overview.html) — hierarchical namespaces and differences from general purpose buckets.
- [How to prevent object overwrites with conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html) — `If-None-Match`, `If-Match`, and contention scenarios.
- [How S3 Versioning works](https://docs.aws.amazon.com/AmazonS3/latest/userguide/versioning-workflows.html) — version IDs, noncurrent versions, and delete markers.
- [Uploading objects using multipart upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html) — completing uploads and managing parts.
- [S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — IAM, Block Public Access, and bucket governance.
- [Replicating objects within and across Regions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html) — data replication and DR checks.
- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) — integrating S3 with asynchronous pipelines.

# Bucket Naming Rules and Object Key Structure Design

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a **bucket name** and an **object key**, and explain why naming affects deployment, access, operations, and Amazon S3 costs.
2. Apply **general purpose bucket** naming rules; choose between the **shared global namespace** and **account regional namespace**.
3. Recognize the naming rules for **directory buckets** and understand why not all rules for general purpose buckets apply to them.
4. Create consistent object keys that are easy to search by **prefix**, while minimizing issues with UTF-8, case sensitivity, slashes, and special characters.
5. Design keys aligned with query patterns, data partitioning, environments, tenants, time, and lifecycle; avoid confusing prefixes with actual security boundaries.
6. Use the AWS CLI to create a sample bucket, write objects, list using prefix/delimiter, and inspect object keys.
7. Evaluate how key design impacts request performance, LIST/PUT/GET costs, IAM policies, lifecycle rules, and scalability.

## 1. Two Naming Levels to Distinguish in Amazon S3

**Amazon Simple Storage Service (Amazon S3)** stores data as **objects** inside **buckets**. An object consists of data (body), metadata, and a **key** that identifies its logical location within the bucket. For a general purpose bucket, you can visualize it as:

```text
s3://company-orders-prod-ap-southeast-1-a1b2c3d4/
      └── orders/year=2026/month=11/day=20/order-8f42.json
          ├── Prefix: orders/year=2026/month=11/day=20/
          └── Full key:
              orders/year=2026/month=11/day=20/order-8f42.json
```

| Component | Example | Scope and Characteristics |
| --- | --- | --- |
| **Bucket name** | `company-orders-prod-ap-southeast-1-a1b2c3d4` | Bucket identifier under S3 namespace rules; does not contain `s3://` or `/`. |
| **Object key** | `orders/year=2026/month=11/day=20/order-8f42.json` | Object identifier **inside the bucket**; includes the entire prefix and final name. |
| **S3 URI** | `s3://company-orders-prod-ap-southeast-1-a1b2c3d4/orders/year=2026/month=11/day=20/order-8f42.json` | Representation of bucket + key for tools and humans; not the raw object key. |
| **Prefix** | `orders/year=2026/` | Leading substring of a key used for grouping and filtering when listing. |
| **Delimiter** | `/` | Character used to group keys when listing; does not automatically create physical folders in a general purpose bucket. |

**Bucket names and keys follow completely different rules:** general purpose bucket names only allow lowercase letters, digits, and certain punctuation, whereas object keys are case-sensitive, support Unicode, and have a maximum length of **1,024 UTF-8 bytes**.

In a general purpose bucket, `reports/2026/summary.csv` and `Reports/2026/summary.csv` are **two different keys**. A key only needs to be unique within the bucket at a given time for the current version. If versioning is enabled on the bucket, the same key can have multiple **object versions**.

## 2. Designing Bucket Names Before Deployment

A good bucket name describes **who owns it**, the **environment**, the **purpose**, and sometimes the **Region**, while still complying with S3 rules. Choosing a bucket name is a long-term decision: **you cannot rename a bucket or change its Region after creation**. If you need a different name or Region, you typically must create a new bucket, copy the data, and update configurations/applications.

Bucket names can appear in URLs, logs, reports, IAM policies, and monitoring tools. **Do not put secrets, customer emails, personal names, tokens, or sensitive data into a bucket name**.

### 2.1. General Purpose Buckets: Syntax Rules

For **general purpose buckets**, the standard rules include:

| Rule | Details |
| --- | --- |
| Length | Between **3 and 63 characters**, including any required suffix if using a special namespace. |
| Allowed characters | Lowercase letters `a-z`, digits `0-9`, hyphens `-`, and periods `.`. |
| First/last character | Must be a **letter or digit**. |
| Periods | Cannot contain two adjacent periods `..`. |
| IP address format | Must not be formatted as an IPv4 address, e.g., `192.168.1.10`. |
| Uppercase, spaces, underscores | Not allowed. |
| Reserved prefixes | Must not start with `xn--`, `sthree-`, or `amzn-s3-demo-`. |
| Reserved suffixes | Must not end with `-s3alias`, `--ol-s3`, `.mrap`, `--x-s3`, or `--table-s3`. |
| `-an` suffix | Only valid when creating a bucket in the **account regional namespace** following the full convention. |

Names ending in `-s3alias`, `.mrap`, and `--x-s3` are reserved for other S3 resources/mechanisms; therefore, do not choose these suffixes for standard general purpose bucket names.

### 2.2. Valid and Invalid Name Examples

| Example Name | Assessment | Explanation |
| --- | --- | --- |
| `storefront-prod-assets-ap-southeast-1-7c4f9e2a` | Syntactically valid | Lowercase, `-` separator, within length limit, includes a suffix to reduce collision risk. |
| `team-a-logs-2026` | Syntactically valid | Simple, readable name; must verify it is still available in the namespace. |
| `my.example.bucket` | Syntactically valid, **not recommended** | Periods can cause issues with virtual-hosted-style HTTPS and Transfer Acceleration. |
| `Storefront-Prod-Assets` | Invalid | Contains uppercase letters. |
| `storefront_prod_assets` | Invalid | Contains underscores. |
| `team..logs` | Invalid | Contains two consecutive periods. |
| `192.168.1.10` | Invalid | Formatted like an IPv4 address. |
| `-prod-assets` | Invalid | Starts with `-`. |
| `prod-assets-` | Invalid | Ends with `-`. |
| `prod.assets--x-s3` | Invalid for general purpose bucket | Suffix reserved for directory buckets. |
| `example-data-111122223333-ap-southeast-1-an` | Valid **if** created in the account regional namespace for that account and Region | Do not assume it is a shared global bucket just because the name matches the format. |

**Syntactic validity does not guarantee creation will succeed.** The name must also be unclaimed in the target namespace and permitted by your account's policies and quotas.

### 2.3. Why Avoid Periods in Bucket Names?

A name like `assets.company.example` may be syntactically valid. However, periods `.` have limitations with **virtual-hosted-style HTTPS**: S3 endpoint wildcard TLS certificates may not match multi-level domain labels. **S3 Transfer Acceleration** also does not allow bucket names containing periods.

Recommendation for modern applications: prefer `assets-company-example` or names without periods, unless you have an explicit requirement such as a matching static website endpoint configuration and have verified full compatibility.

## 3. Namespaces: Bucket Name Uniqueness

### 3.1. Shared Global Namespace

For **general purpose buckets** in the shared global namespace, the name must be **unique across all AWS accounts and all Regions within the same AWS partition**. An AWS partition is an independent group of Regions, such as `aws`, `aws-cn`, `aws-us-gov`, and `aws-eusc`.

For example: if account A has already created `company-orders-prod-ap-southeast-1-a1b2c3d4` in Singapore within the `aws` partition, account B cannot use **that exact name** to create a general purpose bucket in Tokyo within the same partition.

Notable risk: if you **delete** a bucket in the shared global namespace, another account can later create a bucket with the same name and potentially receive requests from legacy systems still targeting that name. If you want to retain control over a published name, consider **emptying the objects and keeping the bucket**, blocking unwanted access rather than deleting the name.

**Do not rely on simply appending `-prod` or `-dev` to guarantee uniqueness.** When using the shared global namespace, append a random identifier/GUID and handle `BucketAlreadyExists` in automated deployments.

### 3.2. Account Regional Namespace

AWS now also offers an **account regional namespace** for general purpose buckets. This is a naming scope dedicated per **AWS account + Region**, ensuring that buckets in this namespace **can only belong to that specific account**, preventing another account from claiming the name.

Format:

```text
<bucket-prefix>-<12-digit-account-id>-<aws-region>-an

Example for account 111122223333 in Singapore:
storefront-prod-assets-111122223333-ap-southeast-1-an
```

Key points:

- The full name still cannot exceed **63 characters**; the account/Region suffix consumes part of the character budget for your custom prefix.
- At creation time, the request must specify the **`account-regional`** namespace (e.g., CLI `--bucket-namespace account-regional` or API header `x-amz-bucket-namespace`).
- Only the matching account can create a bucket with this suffix; if the name is already used by that account, a duplicate with the same name cannot be created.
- It is still a **general purpose bucket**, with the same standard S3 capabilities and requiring IAM/Block Public Access like any other bucket.
- Feature availability depends on the AWS Region; per current documentation, exceptions exist in certain Middle East Regions, so check the support matrix before standardizing organization-wide.

**Recommendation:** when bucket type, Region, and service integrations permit, prefer the account regional namespace to guarantee long-term name ownership. The shared global namespace remains useful when specific compatibility/architecture requirements apply or a Region is not yet supported.

### 3.3. Recommended Bucket Naming Conventions

With the shared global namespace:

```text
<service>-<environment>-<purpose>-<region>-<unique-suffix>

storefront-prod-assets-ap-southeast-1-7c4f9e2a
payments-prod-receipts-ap-southeast-1-4d92a1bf
analytics-dev-raw-ap-northeast-1-6ca37e90
```

With the account regional namespace:

```text
<service>-<environment>-<purpose>-<account-id>-<region>-an

storefront-prod-assets-111122223333-ap-southeast-1-an
analytics-dev-raw-111122223333-ap-northeast-1-an
```

These are **design conventions**, not AWS-enforced syntax for the `service/environment/purpose` segments. Standardize environment values (for example, only `prod`, `staging`, `dev`) so you do not end up with `production`, `prd`, and `prod` mixed across an organization. Avoid using team or department names that change frequently if the bucket needs to persist for years.

## 4. Directory Bucket Names Differ from General Purpose Buckets

Amazon S3 provides **directory buckets** for supported workloads and features, typically associated with S3 Express One Zone or directory-style bucket configurations. Their rules **differ** from general purpose buckets.

A directory bucket name follows this format:

```text
<base-name>--<zone-id>--x-s3

Example:
media-cache--apne1-az1--x-s3
```

The name must be **unique within the selected Zone** (Availability Zone or Local Zone), be **3–63 characters long including the suffix**, use only lowercase letters, digits, and `-`, and start and end with a letter or digit. It must include a suffix containing the **Zone ID** and `--x-s3`; periods are not allowed. Certain reserved prefixes/suffixes similar to general purpose buckets are also invalid.

Comparison:

| Criterion | General Purpose Bucket | Directory Bucket |
| --- | --- | --- |
| Name | Shared global or account regional namespace. | `base-name--zone-id--x-s3`. |
| Uniqueness scope | Within the chosen namespace by partition/account. | Within the bucket's **Zone**. |
| Period character | Allowed by syntax rules, though usually best avoided. | Not allowed. |
| Key organization | Flat namespace; prefixes simulate folders. | **Hierarchical directory namespace** per supported directory bucket capabilities. |
| Delimiter | Any delimiter can be used for listing; `/` is common. | `/` has a dedicated role in the directory model; check API requirements. |
| APIs/features | Full general purpose bucket capabilities. | Different endpoints, LIST behavior, conditions, and APIs; do not assume complete parity. |

**This lesson is primarily designed for general purpose buckets.** When choosing a directory bucket, consult the dedicated documentation for keys, directories, endpoints, and bucket creation. Also distinguish **S3 Tables table buckets**: that is a specialized bucket type for tabular data, with its own naming rules and reserved `--table-s3` suffix.

## 5. Object Keys: The True Identity of Each Object

For a general purpose bucket, an **object key** is a UTF-8 encoded Unicode string up to **1,024 bytes** long. This limit counts the **entire string**, including prefixes, `/` characters, and the final filename.

Example:

```text
images/products/2026/11/sku-1002-front.webp
└───────────── prefix ────────────┘└─object name─┘

Full key:
images/products/2026/11/sku-1002-front.webp
```

Important notes:

- **Case-sensitive:** `Customers/a.json` and `customers/a.json` are two distinct keys.
- **UTF-8 measured in bytes:** accented characters (such as Vietnamese diacritics) often take more than 1 byte; 1,024 Unicode characters do **not** necessarily fit in 1,024 bytes.
- **Slashes are part of the key:** `docs/a.pdf` and `docs//a.pdf` are two different keys.
- **Extensions are an application convention:** `.json`, `.jpg`, `.parquet` help humans and tools recognize data types, but S3 does not require keys to have extensions.
- **The full key is the identity:** moving an object to a new key in a general purpose bucket usually means **copying and then deleting** the old object, which can incur request/data transfer costs and affect versioning/retention.

### 5.1. What Is a "Folder" in a General Purpose Bucket?

General purpose buckets use a **flat namespace**. There is no physical directory tree like on an OS filesystem. The S3 console displays folders by grouping keys by **prefix** and delimiter:

```text
s3://storefront-prod-assets.../
    products/1002/front.webp
    products/1002/back.webp
    products/1003/front.webp
    reports/2026/11/sales.csv
```

You do not need to run a command to create a folder before writing `products/1002/front.webp`. When a user clicks **Create folder** in the S3 console, the console may create an empty (0-byte) object with a trailing `/` key such as `products/1002/` as a visual placeholder. That empty object **is a real object** and can appear in listings and incur request charges, unlike a prefix inferred from existing keys.

### 5.2. Prefixes and Delimiters for Listing

Suppose a bucket contains four keys:

```text
orders/2026/11/20/a.json
orders/2026/11/20/b.json
orders/2026/11/21/c.json
images/products/p01.webp
```

If you call `ListObjectsV2` with `Prefix=orders/2026/11/20/`, the response includes only keys starting with that string. If you call `Prefix=orders/2026/11/` and `Delimiter=/`, the API can group keys below that level into `CommonPrefixes` such as `orders/2026/11/20/` and `orders/2026/11/21/`.

**A prefix is not a SQL filter.** S3 cannot evaluate conditions like "all orders with total amount over one million" if that information only exists inside the JSON body. You must design keys around common access patterns or use metadata, a database, a catalog/Athena, or a dedicated search service.

## 6. Special Characters, Unicode, and URLs

S3 permits a wide range of UTF-8 characters in object keys, but HTTP stacks, SDKs, CLIs, XML parsers, and downstream tools may handle special characters differently. Standardize on an **interoperability-friendly** character set for new systems.

### 6.1. Preferred Conventions

| Character Group | Recommendation |
| --- | --- |
| Letters `a-z`, `A-Z`, digits `0-9` | Supported; typically standardize on lowercase for machine-generated keys to avoid confusion. |
| `-`, `_`, `.` | Use when meaningful; avoid a trailing period at the end of a key. |
| `/` | Use consistently as the logical hierarchy delimiter. |
| Spaces and Unicode | Allowed, but verify Unicode normalization and URL encoding; consider replacing spaces with `-`. |
| `?#%&+`, control characters, or newlines | Can break URL encoding, shells, XML, or parsers; avoid in machine-generated keys. |
| `.` and `..` segments | Avoid: many libraries/tools normalize relative paths, unintentionally altering the key. |

Examples:

| Object Key | Assessment |
| --- | --- |
| `documents/2026/11/invoice-8f42.pdf` | Good: readable, stable, easy to list. |
| `users/42/avatar-4e2f.webp` | Good if the ID is controlled and the user has proper authorization. |
| `reports/BaoCaoTháng11.xlsx` | Valid if within the UTF-8 byte limit, but test encoding across the pipeline. |
| `reports/2026/./nov.csv` | Avoid: `.` segment may be normalized away. |
| `reports/2026/../nov.csv` | Avoid: `..` segment may be treated as a relative path traversal by tools. |
| `users/alice@example.com/profile.json` | Not recommended: exposes email in keys/logs/URLs; use a pseudonymous ID. |
| `exports/result.csv.` | Avoid: the S3 console may strip trailing periods upon download. |

Keys starting with `./` cannot be uploaded via the S3 console in the usual way; keys containing `..` segments are also subject to specific validation rules and easily cause unexpected behavior. A key equal to `soap` has restrictions with **virtual-hosted-style requests**; avoid using it for objects accessed via that URL style.

### 6.2. Object Keys vs. Encoded URL Paths

Suppose an object key is:

```text
images/holiday photo #1.jpg
```

When building an HTTP URL, spaces and `#` must be **percent-encoded** per URI rules; otherwise `#1.jpg` may be interpreted by browsers as a URL fragment rather than part of the key. Likewise, `+` can be interpreted as a space by some intermediaries.

**Never take raw user input and concatenate it directly into a public URL.** Prefer AWS SDKs, presigned URLs, or standard URI encoding functions, and test UTF-8 and special characters thoroughly.

With Unicode, the same visually identical character can be represented by different byte sequences (for example, precomposed vs. decomposed Unicode). S3 compares **keys by raw UTF-8 bytes**; if an application accepts user text, **normalize Unicode** to a consistent form before generating keys.

### 6.3. Avoid Confusing Keys with OS File Paths

On Windows, file paths use `\`, whereas S3 keys should use `/`. Example local path:

```text
C:\exports\2026\11\orders.json
```

When uploading, explicitly map it to the key:

```text
exports/2026/11/orders.json
```

Never pass drive letters, hostnames, absolute paths, or user-supplied `..` segments directly into keys without validation. Keys should be stable, application-safe logical identifiers independent of the uploading machine's OS.

## 7. Designing Keys Around Access Patterns and Data Lifecycle

A good key convention answers: **who owns it? what type of data is it? how will it be listed? when is it deleted or transitioned to another storage class? could parallel writes collide?**

### 7.1. Start from Query Patterns

For example, an e-commerce platform typically needs to:

- Retrieve a single invoice by ID.
- List logs for a specific day.
- Process raw data in daily and Regional batches.
- Scope data access per tenant.

We can choose:

```text
invoices/year=2026/month=11/id=inv-8f42.pdf
logs/service=checkout/year=2026/month=11/day=20/part-001.jsonl.gz
raw/source=payments/region=ap-southeast-1/year=2026/month=11/day=20/batch-0f1a.parquet
tenants/t-6f2d/assets/images/avatar-fc24.webp
```

Keys have **prefixes tailored for `ListObjectsV2`**, not merely for visual folder presentation. For instance, if you need to list November logs, `logs/service=checkout/year=2026/month=11/` is far more effective than putting everything in `all-logs/random-file` and scanning the entire bucket.

### 7.2. How Should Key Segments Be Ordered?

| Common Access Pattern | Suggested Prefix | Trade-offs to Consider |
| --- | --- | --- |
| By service, then date | `logs/service=checkout/year=2026/month=11/day=20/` | Great when operators frequently query one service over a date range. |
| By tenant, then dataset | `tenants/t-6f2d/dataset=orders/year=2026/` | Easy to pair with tenant/prefix IAM policies when scoped properly, though tenant IDs do not create security on their own. |
| By date, then source | `landing/date=2026-11-20/source=payments/` | Convenient for batch jobs processing all sources for a given day. |
| By exact ID | `invoices/by-id/8f/42/inv-8f42.pdf` | Creates deterministic lookup keys; the application must know the hashing/prefix-sharding rule. |

No single prefix order is optimal for every query. Optimize for the most frequent queries/jobs, and consider a separate **catalog/index** when multi-dimensional queries are needed. Duplicating the same object under multiple keys to serve different query patterns increases storage, request counts, and lifecycle management overhead.

### 7.3. Partition Design for Data Lakes

In a data lake, `key=value` conventions generally integrate well with tools supporting Hive-style partitioning:

```text
dataset=orders/ingest_date=2026-11-20/region=ap-southeast-1/part-0001.parquet
dataset=orders/ingest_date=2026-11-20/region=ap-northeast-1/part-0002.parquet
dataset=orders/ingest_date=2026-11-21/region=ap-southeast-1/part-0003.parquet
```

When designing, clearly define:

1. Does `ingest_date` mean **ingestion date** or business event date (`event_date`)? The two fields have different semantics.
2. Time convention: **UTC** or business local timezone? Avoid one pipeline using UTC and another using local time under the same partition name.
3. Should you partition by `region`, `tenant`, `service`? Too many tiny partitions create many small files, hurting processing performance and increasing request/catalog costs.
4. Do you have mechanisms for **late-arriving data**, replays, idempotency, and partition-level data deletion?

**S3 does not automatically create table or partition metadata for Athena/Glue just because keys contain `year=`.** You must manage the catalog and ingestion/query configuration properly.

### 7.4. Preventing Overwrites with Concurrent Producers

If all workers write to `uploads/latest.json`, contention or unintended overwrites can happen. An alternative design:

```text
uploads/year=2026/month=11/day=20/6fae77a0-c3a7-4d30-a153-aed42af91e8a.json
uploads/year=2026/month=11/day=20/e8a106bf-b5aa-4058-9fa2-7893abcb439d.json
```

Use unique IDs such as UUIDs/ULIDs or business-assigned IDs, along with a clear retry policy. If an event must be **idempotent**, derive the key from a stable event ID, use conditional writes (such as `If-None-Match: *` via supported APIs/SDKs), or coordinate tasks using a database/queue.

**Bucket versioning** preserves multiple object versions under the same key when enabled and configured properly; it helps recover from overwrites or deletes but **does not replace** concurrency design and deduplication mechanisms. Versioning can also add storage costs for older versions.

## 8. Prefixes, Security, and Access Permissions

A key such as `tenants/t-6f2d/private/contract.pdf` **is not automatically private** simply because it contains the word `private`. Actual access depends on IAM policies, bucket/access point policies, S3 Block Public Access, Object Ownership, encryption, and related controls.

### 8.1. ListBucket and GetObject Are Separate Permissions

For general purpose buckets:

- `s3:ListBucket` applies to the **bucket ARN** and can restrict requested prefixes via the `s3:prefix` condition.
- `s3:GetObject` applies to the **object ARN**, such as `arn:aws:s3:::bucket-name/tenants/t-6f2d/*`.

Illustrative IAM policy **for a role** allowed only to list and read objects within a specific tenant prefix, with the bucket name replaced by the real bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyTenantPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::storefront-prod-assets-ap-southeast-1-a1b2c3d4",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "tenants/t-6f2d/",
            "tenants/t-6f2d/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadOnlyTenantObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::storefront-prod-assets-ap-southeast-1-a1b2c3d4/tenants/t-6f2d/*"
    }
  ]
}
```

**This policy alone does not guarantee complete tenant isolation.** You must also consider other policies, explicit Denies, upload/delete permissions, KMS keys, presigned URLs, role assumption, access points, and application input validation. If the role already has broad S3 permissions elsewhere, a narrow `Allow` statement does not revoke those broader permissions.

### 8.2. Validating User Input Before Assembling Keys

Suppose an API receives `tenantId` and `filename` from a request:

```text
tenants/<tenantId>/uploads/<filename>
```

Never trust a client-supplied `tenantId` as proof of authorization, and never allow `filename` to inject `../`, `/`, or characters that break the intended structure. The server should authenticate the user, derive the tenant ID from verified tokens/authorization state, sanitize/restrict the filename, generate independent IDs, and issue presigned URLs only for authorized locations.

**Key names are not an encryption mechanism.** Avoid placing emails, phone numbers, secret codes, or personal data in prefixes/keys, as keys can appear in logs, URLs, audits, and reports.

## 9. Impact of Prefixes on Performance and Cost

### 9.1. Modern S3 Performance

Amazon S3 scales automatically with traffic and can achieve at least **3,500 PUT/COPY/POST/DELETE** or **5,500 GET/HEAD** requests per second **per partitioned prefix** for general purpose buckets, depending on the workload pattern. You can leverage **multiple prefixes** and parallel requests for high-throughput workloads.

Key points to understand accurately:

- These are **request rate** capabilities, not a promise that every application immediately receives that rate under every pattern.
- Scaling happens **gradually**; sudden traffic spikes can trigger HTTP `503 Slow Down` responses requiring retries with **exponential backoff and jitter**.
- **It is not mandatory** to prepend random hashes to all object keys. Design primarily for query and operational patterns; distribute across multiple prefixes only when actual workload characteristics require it.
- For massive parallel processing, you can distribute work across prefixes such as `shard=00/`, `shard=01/`, ..., provided readers know the sharding scheme to retrieve data.

For example, `logs/service=checkout/year=2026/month=11/day=20/` works well for daily queries. If all workers writing to a single prefix exceed serving capacity, you can add `shard=00..15/` or group prefixes by workload to distribute requests. Do this only once metrics justify it and you have a clear listing strategy.

### 9.2. Costs Stem from Key Usage Patterns, Not Just Stored Bytes

Cost factors to evaluate include:

| Component | Impact of Key Design |
| --- | --- |
| **PUT/COPY/POST/LIST** | Many tiny objects or frequent prefix scans can drive up request counts. |
| **GET/HEAD** | Reading individual objects increases request volume; file count and sizing affect processing cost. |
| **Storage** | Duplicate object copies, old versions, lifecycle transitions, and storage classes affect volume/fees. |
| **Inventory/analytics** | S3 Inventory or catalogs can analyze objects instead of repeatedly listing the whole bucket. |
| **Data transfer** | Downloads and egress out of AWS have separate pricing regardless of how clean your keys are. |

Consistent prefixes make it straightforward to configure **Lifecycle rules** by prefix or tag—such as transitioning `logs/` to another storage class or expiring objects per retention policy. However, prefixes **do not automatically trigger** lifecycle actions; you must define and test the rules. Always check retention, Object Lock, versioning, and legal requirements before expiring data.

### 9.3. Do Not Use Keys as a Universal Indexing System

S3 supports retrieval by **bucket + key** and listing by prefix. When you need queries like "all orders for user X across all months," "all overdue invoices," or "full-text search," consider:

- **DynamoDB/RDS** to store IDs and keys for direct lookup.
- **AWS Glue Data Catalog/Athena** for partitioned analytics datasets.
- **S3 Inventory** to reconcile large volumes of objects/keys/metadata.
- **OpenSearch** or a dedicated search service if content search is required.

Good key design reduces complexity, but does not replace a relational database, secondary indexes, or analytics engines.

## 10. AWS CLI Hands-On: Creating a Bucket and Testing Key Structures

The examples below use a **general purpose bucket** in `ap-southeast-1`. Run them in a test environment with the AWS CLI properly configured and appropriate IAM permissions. Buckets and objects incur storage and request charges; use real names that you own.

### 10.1. Verify Identity Before Creating

```bash
aws sts get-caller-identity
aws configure get region
```

From the output, note your **AWS account ID** and selected Region. Do not run bucket creation commands against the wrong production account.

### 10.2. Create a Shared Global Namespace Bucket

Example using a distinguishing suffix (may already be claimed; change the suffix before running):

```bash
aws s3api create-bucket \
  --bucket storefront-dev-assets-ap-southeast-1-7c4f9e2a \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1
```

For Regions outside `us-east-1`, a matching `LocationConstraint` is required. `us-east-1` itself has different bucket creation rules; do not copy the command above and only swap the Region without checking.

If you receive `BucketAlreadyExists`, the shared global name is owned by another account. If `BucketAlreadyOwnedByYou`, no recreation is needed. Do not automatically delete existing buckets just to "free up" a name.

### 10.3. Create an Account Regional Namespace Bucket

If account `111122223333` and Region `ap-southeast-1` apply, for example:

```bash
aws s3api create-bucket \
  --bucket storefront-dev-assets-111122223333-ap-southeast-1-an \
  --bucket-namespace account-regional \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1
```

**Replace `111122223333` with your actual account ID** before running, and check name length and Region support. A name ending in `-an` without `--bucket-namespace account-regional` will not create the bucket in this namespace type.

You only need to choose **one of the two** bucket examples for the lab; the steps below use `$BUCKET` for the created bucket name:

```bash
# Use a real bucket name belonging to your lab account.
BUCKET="storefront-dev-assets-ap-southeast-1-7c4f9e2a"
REGION="ap-southeast-1"

aws s3api head-bucket --bucket "$BUCKET" --region "$REGION"
```

The `head-bucket` command confirms accessibility under current permissions; an error may indicate the bucket does not exist, access is denied, or the Region is wrong. You can check the Region using `get-bucket-location` or response headers if permitted.

### 10.4. Upload an Object with Its Full Key

Suppose your machine has a file `order.json` containing valid JSON. Example:

```json
{
  "orderId": "ord-8f42",
  "createdAt": "2026-11-20T02:00:00Z",
  "status": "received"
}
```

Upload:

```bash
aws s3api put-object \
  --bucket "$BUCKET" \
  --key "orders/year=2026/month=11/day=20/order-8f42.json" \
  --body "./order.json" \
  --content-type "application/json" \
  --region "$REGION"
```

There is no need to create `orders/`, `orders/year=2026/`, or `.../day=20/` folders beforehand. Given valid IAM permissions and bucket settings, the object is stored at the exact **full key**. If the same key already exists and versioning is off, a subsequent write overwrites the current object; choose an appropriate overwrite-prevention strategy.

Inspect the object:

```bash
aws s3api head-object \
  --bucket "$BUCKET" \
  --key "orders/year=2026/month=11/day=20/order-8f42.json" \
  --region "$REGION"
```

`head-object` returns metadata such as `ContentLength`, `ContentType`, and `LastModified` if permissions and paths are valid, without downloading the entire body.

### 10.5. List Objects Using Prefix and Delimiter

List orders for November 20:

```bash
aws s3api list-objects-v2 \
  --bucket "$BUCKET" \
  --prefix "orders/year=2026/month=11/day=20/" \
  --region "$REGION" \
  --query 'Contents[].Key'
```

Group by day within the month:

```bash
aws s3api list-objects-v2 \
  --bucket "$BUCKET" \
  --prefix "orders/year=2026/month=11/" \
  --delimiter "/" \
  --region "$REGION" \
  --query '{Objects:Contents[].Key,Prefixes:CommonPrefixes[].Prefix}'
```

When the object count is large, handle **pagination**; a single API response caps the number of returned items, while the AWS CLI paginates by default and exposes `--max-items`/`--starting-token` when explicit control is needed. Never write code that reads only the first page and assumes that is all the objects under a prefix.

### 10.6. Verify Case Sensitivity in Keys

If you upload two keys:

```text
exports/Report.csv
exports/report.csv
```

You will have two separate objects. Define a strict convention for your application (such as lowercase for all machine-generated prefixes and keys) to prevent hard-to-spot duplicates, especially when users upload files from Windows or case-insensitive systems.

### 10.7. Lab Cleanup

If you only created a test bucket **containing no real data**, you can delete the lab objects and then delete the bucket following standard S3 procedures. For a versioning-enabled bucket, deleting all **current objects** does not necessarily empty the bucket: object versions and delete markers may remain. Never run `aws s3 rb --force` carelessly on buckets containing shared data.

For buckets with a published, fixed name in the shared global namespace, consider **keeping the empty bucket** to protect the name rather than deleting it, as noted in section 3.

## 11. Naming Design Workflow for a Real-World System

Scenario: a company builds an e-commerce application with two environments, `prod` and `dev`, storing product images, PDF invoices, and order processing logs in Singapore. Requirements:

- Restrict public access; issue valid download URLs only to authorized users.
- Separate environments and data purposes.
- List logs by date/service, look up invoices by ID, and recover from overwrites.
- Apply lifecycle policies to logs and track costs.

### 11.1. Proposed Buckets

| Purpose | Illustrative Shared Global Name | Policy Suggestions |
| --- | --- | --- |
| Production product images | `storefront-prod-assets-ap-southeast-1-7c4f9e2a` | Block Public Access, grant appropriate application/CloudFront permissions. |
| Production invoices | `storefront-prod-invoices-ap-southeast-1-8b1d27c4` | Data protection, encryption, versioning/retention as required. |
| Production logs | `storefront-prod-logs-ap-southeast-1-1ea40b23` | Lifecycle rules and dedicated write/read permissions for pipelines/log consumers. |
| Development resources | `storefront-dev-assets-ap-southeast-1-66d8a2f1` | Avoid real customer data unless strictly necessary. |

If choosing the account regional namespace, replace the random suffix with `-<account-id>-ap-southeast-1-an` per the naming rules and 63-character limit. The examples above only illustrate syntax and may not be available for creation.

### 11.2. Proposed Object Keys

```text
# Assets: each image has a stable key by product and image ID
products/p-1002/images/img-6f2a.webp

# Invoices: direct lookup by invoice ID, no exposed email
invoices/year=2026/month=11/inv-8f42.pdf

# Logs: listable by service/date, with unique ID to prevent overwrites
logs/service=checkout/year=2026/month=11/day=20/part-8e2a.jsonl.gz
logs/service=payments/year=2026/month=11/day=20/part-d4c1.jsonl.gz
```

The application should store the `invoiceId → bucket + key` mapping in a database if frequent retrieval is needed without knowing the month, since `ListObjectsV2` is not a database query. For sensitive data, restrict permissions by bucket/prefix/role and issue time-limited presigned URLs when distributing objects.

### 11.3. Decisions by Data Lifecycle

1. **Product images:** immutable keys when each upload creates a new image; update metadata/database pointers to the new key or manage versioning if needed.
2. **Invoices:** stable IDs, strict edit/delete controls, appropriate retention/backup; keys must not contain customer names or emails.
3. **Logs:** prefixes by `service` and `date` for easy listing and lifecycle rules; independent object names so parallel workers do not overwrite each other.
4. **Dev:** separate bucket/role; shorter lifecycle where appropriate, monitor storage and request costs.
5. **All:** least-privilege IAM, appropriate default encryption, Block Public Access, logging/auditing, and a change procedure for migrating keys or buckets.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| `InvalidBucketName` when creating a bucket | Uppercase letters, `_`, consecutive periods, invalid length/suffix. | Compare against naming rules for the target bucket type/namespace. |
| `BucketAlreadyExists` | Shared global name is already owned by another account in the partition. | Choose a different name, add a GUID, or use the account regional namespace. |
| `BucketAlreadyOwnedByYou` | Your account already owns a bucket with that name. | Check existing buckets and Region; do not recreate. |
| Error creating an account regional bucket | Wrong account ID/Region in suffix, missing `--bucket-namespace`, or unsupported Region. | Verify the exact `prefix-account-region-an` format and request parameters. |
| HTTPS certificate error on a bucket with periods | Virtual-hosted-style TLS wildcard does not match multi-level names. | Avoid periods or configure a supported endpoint/certificate setup. |
| `NoSuchKey` even though the console "looks like the same name" | Case mismatch, Unicode characters, spaces, `/`, or URL encoding issues. | Copy the exact key from metadata/ListObjects; inspect raw bytes/URL. |
| Uploaded file doesn't appear under the expected folder | Missing or extra prefix/slash in the key. | Check the **full key** in the upload response and via `head-object`. |
| Prefix listing misses objects | Wrong prefix, non-key filter assumption, or unhandled pagination. | Check `Prefix`, `Delimiter`, and continuation tokens. |
| `AccessDenied` on list/read | Missing `s3:ListBucket`/`s3:GetObject` or blocked by policy/KMS/SCP. | Inspect bucket ARN, object ARN, and policy conditions. |
| `503 Slow Down` on GET during sudden traffic spikes | S3 is partitioning/scaling or traffic is overly concentrated. | Retry with exponential backoff; distribute across multiple prefixes if needed. |
| Bucket deletion fails | Remaining objects, versions, delete markers, multipart uploads, or other constraints. | Inventory and clean up the exact resources; never blindly delete shared buckets. |

## 13. Scenario Exercise

**Context:** an enterprise has 12 AWS accounts and deploys S3 in Singapore and Tokyo. The data team wants to store daily logs, the application team wants to distribute product images, and accounting must retain invoices for many years. Currently, bucket names are inconsistent like `Data`, `files_prod`, and `my.company.logs`; log keys look like `log1.json`, `log2.json`, making them hard to query.

Design the following:

1. A bucket naming convention usable in the **account regional namespace**, showing how to distinguish service, environment, purpose, account, and Region.
2. Valid bucket names for the three data categories; illustrative names must comply with the 63-character limit.
3. Key conventions for invoices by ID, images by product, and logs by service/date.
4. A prefix query to list logs for `2026-11-20`.
5. An IAM policy granting read-only access strictly to `tenants/t-6f2d/` without granting access to other tenants.
6. A deduplication/collision-avoidance plan when 100 workers upload simultaneously.
7. A lifecycle rule targeting the log prefix and a way to measure storage/request costs.

**Hints:** choose the namespace before creating buckets; calculate suffix length; use stable keys or immutable IDs; avoid sensitive data; base policies on bucket ARN + object ARN; measure request rates before adding random shards; use a catalog/index when multi-dimensional queries are needed.

## 14. Common Misconceptions

**Misconception 1: "Bucket names only need to be unique within my Region."**  
False for the **shared global namespace** of general purpose buckets: names must be unique across the entire partition. The account regional namespace uses separate account+Region rules.

**Misconception 2: "You can rename a bucket after creating it."**  
False. Changing a name or Region normally requires a new bucket and a plan to migrate data, permissions, endpoints, and references.

**Misconception 3: "Folders are real resources in every S3 bucket."**  
False for **general purpose buckets**: prefixes simulate hierarchy. However, **directory buckets** do have a hierarchical namespace and separate rules—do not conflate the two.

**Misconception 4: "S3 object keys are case-insensitive."**  
False. `Reports/a.csv` and `reports/a.csv` are two independent keys.

**Misconception 5: "Object keys can be up to 1,024 Vietnamese characters long."**  
False. The limit is **1,024 UTF-8 bytes**, including prefixes and delimiters.

**Misconception 6: "Using the prefix `tenants/t-123/private` automatically secures the data."**  
False. A prefix is just part of the key string; security requires IAM, bucket/access point policies, Block Public Access, encryption, and identity verification.

**Misconception 7: "You must always prepend a hash to keys for good S3 performance."**  
False. S3 scales automatically; splitting across prefixes is a strategy for when actual traffic demands it, not a replacement for access-pattern design.

**Misconception 8: "`ListObjectsV2` supports arbitrary search conditions."**  
False. S3 lists by prefix and delimiter; it does not filter attributes inside object bodies like SQL.

**Misconception 9: "Deleting a bucket and recreating it always lets you reclaim the old name."**  
False for the shared global namespace: another account can register the name. For the account regional namespace, ownership rules differ, though you still cannot create a bucket with a name that currently exists.

**Misconception 10: "If periods are valid in a bucket name, they work seamlessly with all features."**  
False. Virtual-hosted-style HTTPS and S3 Transfer Acceleration have restrictions with periods.

## 15. Self-Check Questions

**Question 1.** Can `Order_Prod` be used to create a general purpose bucket?  
**Answer:** No. It contains uppercase letters and an underscore `_`.

**Question 2.** In the shared global namespace, can two accounts in Singapore and Tokyo create buckets with the same name?  
**Answer:** No, if they are in the same AWS partition. General purpose bucket names in the shared global namespace must be unique across the partition.

**Question 3.** What does the suffix `-111122223333-ap-southeast-1-an` indicate?  
**Answer:** The account regional namespace for account `111122223333` in Region `ap-southeast-1`. The matching namespace must be specified when calling CreateBucket.

**Question 4.** Does the object key `reports/2026/11/a.csv` "reside in a physical folder" named `reports` inside a general purpose bucket?  
**Answer:** No. It is a flat key; `reports/` is a logical prefix used by the S3 console/CLI to group objects.

**Question 5.** Why might the key `Báo cáo/2026.xlsx` take up more bytes than its character count?  
**Answer:** Because UTF-8 uses multiple bytes for certain Unicode characters. The key limit is 1,024 **bytes**.

**Question 6.** When listing objects with the prefix `logs/year=2026/month=11/`, does S3 automatically filter file contents by transaction date inside the JSON?  
**Answer:** No. Only keys starting with that prefix are evaluated; file contents are not a condition in `ListObjectsV2`.

**Question 7.** Can a bucket with periods like `my.company.assets` be created, and should it be used?  
**Answer:** It may be syntactically valid, but should be avoided if virtual-hosted-style HTTPS or S3 Transfer Acceleration is needed due to period restrictions.

**Question 8.** If a user has `s3:GetObject` on object ARNs under `tenants/t-6f2d/*`, can they list all objects in the bucket?  
**Answer:** No. `s3:ListBucket` is a separate bucket-level permission; an IAM policy must explicitly allow listing, typically restricted with `s3:prefix`.

**Question 9.** What is the risk when multiple workers simultaneously write to `uploads/latest.json`?  
**Answer:** Contention/overwrites. Use immutable keys per event/UUID, conditional writes, versioning, and idempotency controls as required.

**Question 10.** For a directory bucket, can you take naming rules from general purpose buckets and apply them directly?  
**Answer:** No. Directory buckets use a Zone ID and `--x-s3` suffix, Zone-scoped uniqueness, and different delimiter and namespace rules.

## Official AWS Documentation

- [General purpose bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html)
- [Namespaces for general purpose buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/gpbucketnamespaces.html)
- [Directory bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-bucket-naming-rules.html)
- [Working with directory buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-buckets-overview.html)
- [Naming Amazon S3 objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html)
- [Organizing objects using prefixes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-prefixes.html)
- [ListObjectsV2 API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html)
- [Performance design patterns for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html)
- [Amazon S3 request performance best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [Amazon S3 access management](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-management.html)
- [AWS CLI — s3api create-bucket](https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html)
- [AWS CLI — s3api list-objects-v2](https://docs.aws.amazon.com/cli/latest/reference/s3api/list-objects-v2.html)

**Key Takeaway:** The **bucket name** defines the identity, ownership scope, and compatibility of the storage container; the **object key** governs how applications access, list, authorize, and manage data lifecycles. For general purpose buckets, choose the right namespace, use clear names that expose no sensitive information, design consistent prefixes/keys around access patterns, handle Unicode/URLs safely, and apply granular IAM permissions. When using **directory buckets** or other S3 bucket types, apply the naming rules and APIs specific to that type.

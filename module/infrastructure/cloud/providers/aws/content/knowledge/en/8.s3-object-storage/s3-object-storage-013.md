# Object Lock, Inventory, Storage Lens, and Batch Operations

> **Chapter:** S3 Object Storage  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; practice designing secure, observable, recoverable, and cost-controlled applications.

When an Amazon S3 bucket holds millions of objects, storage governance goes far beyond uploading and downloading. Organizations must also answer questions like: **How do we prevent accidental deletion of records required for 7 years? How do we pinpoint which objects lack encryption or retention policies? How do we track cost trends? How do we remediate millions of objects without writing risky ad-hoc loop scripts?**

These four features solve distinct parts of that challenge:

| Feature | Core Question | Typical Output |
| --- | --- | --- |
| **S3 Object Lock** | Which object versions must be protected against deletion/overwrites until when? | Retention periods, **Governance/Compliance** modes, **Legal Hold** |
| **S3 Inventory** | Which objects/versions currently exist in the bucket and what are their attributes? | Scheduled reports in **CSV, ORC, or Parquet** stored in a destination bucket |
| **S3 Storage Lens** | What are storage volume, object counts, activity, protection coverage, and trends? | Dashboards, metrics, and breakdowns by account/Region/bucket and supported granularities |
| **S3 Batch Operations** | How do we execute the same action across massive numbers of objects/versions? | **Jobs** reading a manifest, running bulk operations, and emitting completion reports |

Key takeaway: **Object Lock protects**, **Inventory catalogs**, **Storage Lens observes trends**, and **Batch Operations executes changes**. None of these four features replaces the other three.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the relationship between Object Lock and S3 Versioning; distinguish Governance, Compliance, Legal Hold, and default retention.
2. Understand why Object Lock protects **object versions** and what happens when `DELETE` omits `versionId`.
3. Design S3 Inventory schedules (daily/weekly), formats, `Current`/`All` version scopes, optional fields, and report delivery permissions.
4. Use S3 Storage Lens to spot usage trends, wasted storage, and data-protection gaps.
5. Plan S3 Batch Operations jobs with manifests, IAM execution roles, scope verification, confirmation, and completion reports.
6. Combine all four features to audit and remediate data at scale while maintaining least privilege and auditability.

## 2. The Big Picture: From Observation to Action

~~~mermaid
flowchart LR
    BUCKET["Source S3 bucket\nObjects + Versioning"]
    LOCK["Object Lock\nRetention / Legal Hold"]
    INV["S3 Inventory\nScheduled reports"]
    LENS["S3 Storage Lens\nMetrics and trends"]
    REPORT["Report bucket\nCSV / ORC / Parquet"]
    REVIEW["Administrator\nReview scope"]
    BATCH["S3 Batch Operations\nManifest-driven job"]
    RESULT["Completion report\nSucceeded / Failed"]

    LOCK -->|"Protects versions"| BUCKET
    BUCKET --> INV
    BUCKET --> LENS
    INV --> REPORT
    LENS --> REVIEW
    REPORT --> REVIEW
    REVIEW -->|"Approve manifest and action"| BATCH
    BATCH -->|"API calls on selected objects/versions"| BUCKET
    BATCH --> RESULT
~~~

*Diagram shows the governance workflow. Inventory and Storage Lens have their own refresh intervals rather than real-time query semantics. Batch Operations remains bound by IAM, bucket policies, KMS, and Object Lock.*

In production architectures, these four capabilities work alongside other layers:

- **IAM / bucket policies / KMS key policies** decide who can read, write, edit retention, and launch jobs.
- **Versioning, backups/replication, Object Lock** support recovery and compliance retention.
- **CloudTrail, CloudWatch, S3 server access logs, or data events** enable investigation and observability per configuration.
- **AWS Budgets / Cost Explorer / Storage Lens** reveal spending and optimization opportunities.

## 3. S3 Object Lock: WORM at the Object Version Level

**S3 Object Lock** provides **Write Once Read Many (WORM)** protection: during the protected period, a **specific object version** cannot be directly deleted or overwritten in violation of retention rules. It fits audit logs, financial records, backups, and regulated archives.

### 3.1. Prerequisites

- Object Lock works on **general purpose buckets** with **S3 Versioning** enabled.
- Once Object Lock is enabled on a bucket, **Versioning is enabled** and cannot be suspended while Object Lock is active.
- Object Lock can be enabled at bucket creation or on existing buckets following AWS guidance. Once enabled on a bucket, **Object Lock cannot be disabled**.
- Not every bucket type, storage class, or S3 API shares identical Object Lock behavior. Verify bucket type and business requirements carefully.

Object Lock binds **retention or a legal hold to an object version**, not just a key string. Writing to the same key creates a **new version**, while prior versions stay protected.

### 3.2. How Retention Differs from Legal Hold

| Attribute | Retention | Legal Hold |
| --- | --- | --- |
| Question | "Until what date should this version be kept?" | "Is this version held for a legal/investigative mandate?" |
| Configuration | **Mode** + **retain-until date** | **ON/OFF** status |
| Duration | Has a defined end timestamp | **Never expires automatically**; must be lifted by an authorized principal |
| Usage | Scheduled retention policies | Litigation, audits, preservation holds |
| Effect | Protects the version until retention expires | Protects the version while hold is ON |

**Retention and Legal Hold are independent mechanisms.** If a version's retention date expires while Legal Hold is still ON, the version remains protected. Conversely, lifting a Legal Hold does not allow deleting a version whose retention period is still active.

### 3.3. Governance Mode vs. Compliance Mode

| Characteristic | **Governance** | **Compliance** |
| --- | --- | --- |
| Goal | Protects against normal deletes/edits while allowing strictly controlled exception overrides | Enforces strict immutability for the entire retention window |
| Can held versions be deleted early? | Only if the principal has **bypass permission** and the request explicitly passes the bypass header | **No IAM permission can bypass** active unexpired retention |
| Can retention be shortened? | Yes, via authorized bypass mechanism | Cannot be shortened once applied in Compliance mode |
| Who should have access? | Very few break-glass operational roles | Choose retention cautiously before writing data |
| Misconfiguration risk | Overly broad `BypassGovernanceRetention` breaks protection | Longer retention than needed locks data undeletable, accruing ongoing storage costs |

In **Governance mode**, to bypass retention on supported operations, the principal needs `s3:BypassGovernanceRetention` **and** the request must include `x-amz-bypass-governance-retention:true`. The AWS Console can pass this header automatically if the signed-in user holds bypass permission; therefore, **strictly restrict the IAM permission**, rather than relying on a UI checkbox.

In **Compliance mode**, AWS prevents deleting or overwriting a **held version** before its retain-until date, even by account administrators or root. Choosing Compliance requires careful operational and compliance review because no admin privilege can shorten applied retention.

### 3.4. Default Retention vs. Per-Version Retention

A bucket can configure **default retention** for newly created objects—for example, Governance for 365 days or Compliance for 7 years. When a new object version is PUT without explicit per-object retention headers, default retention applies per bucket settings.

~~~text
General purpose bucket: audit-ledger-example
Object Lock: enabled
Versioning: enabled
Default retention: GOVERNANCE, 365 days

PUT audit/2026/tx-0001.json  -> version v1, retained until policy date
PUT audit/2026/tx-0001.json  -> new version v2, retention evaluated separately
~~~

Details easily missed:

- Enabling default retention **does not retroactively apply** to pre-existing objects or versions. Protecting older versions requires an explicit workflow applying retention to each target version.
- Per-object/version retention headers and bucket default retention interact per AWS rules; review behavior before building upload pipelines.
- A version's retention can be **extended** per rules; whether it can be **shortened** or changed in mode depends on the active mode and permissions.
- When locking data for years, check **lifecycle policies**: storage-class transitions and version expirations must respect active retention and compliance holds.

### 3.5. What Happens When You DELETE a Key Under Object Lock?

In a versioning-enabled bucket, calling `DELETE Object` **without a version ID** simply inserts a **delete marker** as the current version. It does **not permanently delete prior versions**, even when protected by Object Lock.

~~~mermaid
sequenceDiagram
    participant U as Application
    participant S as Bucket with Versioning + Object Lock
    U->>S: PUT record.json
    S-->>U: Version v1, retained
    U->>S: DELETE record.json (no version ID)
    S-->>U: Creates current delete marker
    U->>S: GET record.json (no version ID)
    S-->>U: No current body returned
    Note over S: Version v1 remains preserved in history
~~~

Attempting to permanently delete **`v1`** via `DELETE` with `versionId=v1` while retention or Legal Hold is active will be denied unless a valid Governance bypass applies. Therefore, audit procedures must inspect **version IDs**, **delete markers**, retention, and legal holds—never just test whether `GET` on the key succeeds.

### 3.6. What Object Lock Does Not Replace

- Not a **read** authorization control: IAM and bucket policies still govern who can view data.
- Does not stop applications from writing **new versions** under the same key; locking old versions is not locking the entire namespace.
- Does not replace backups, restore drills, replication, or protection against application logic bugs.
- Does not prevent accidental deletion **after retention expires**; lifecycle and delete permissions still matter.
- Not a "mutex" or optimistic lock for two workers updating the same key concurrently.

## 4. Designing IAM for Object Lock

Key IAM actions to distinguish:

| Action | Meaning |
| --- | --- |
| `s3:GetBucketObjectLockConfiguration` | Read bucket-level Object Lock configuration |
| `s3:PutBucketObjectLockConfiguration` | Modify bucket-level Object Lock / default retention |
| `s3:GetObjectRetention` | Read retention on a specific object version |
| `s3:PutObjectRetention` | Set or update retention where permitted |
| `s3:GetObjectLegalHold` | Read Legal Hold status |
| `s3:PutObjectLegalHold` | Turn Legal Hold ON/OFF per permissions |
| `s3:BypassGovernanceRetention` | Permit bypassing Governance retention on valid requests |
| `s3:DeleteObjectVersion` | Delete a specific version, still subject to Object Lock |

**Design principle:** separate read-only audit, bucket config, retention assignment, Legal Hold management, and Governance bypass into distinct roles. In particular, **`s3:BypassGovernanceRetention` must never be attached to daily upload/ETL roles**.

Illustrative **read-only identity policy for inspecting Object Lock state** on a bucket and its objects:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadBucketObjectLockConfig",
      "Effect": "Allow",
      "Action": "s3:GetBucketObjectLockConfiguration",
      "Resource": "arn:aws:s3:::audit-ledger-example"
    },
    {
      "Sid": "ReadObjectRetentionAndLegalHold",
      "Effect": "Allow",
      "Action": [
        "s3:GetObjectRetention",
        "s3:GetObjectLegalHold"
      ],
      "Resource": "arn:aws:s3:::audit-ledger-example/*"
    }
  ]
}
~~~

This grants permission only to **read Object Lock metadata**—not `s3:GetObject` to read object bodies, lift holds, or edit retention. Workflows listing versions also require `s3:ListBucketVersions` on the bucket ARN. Final effective access still depends on IAM, bucket policies, SCPs, permissions boundaries, KMS, and other policy layers.

### 4.1. Inspecting via AWS CLI (Read-Only)

Assuming `audit-ledger-example` and `records/2026/event-0001.json` are placeholders for an authorized environment:

~~~bash
aws s3api get-object-lock-configuration \
  --bucket audit-ledger-example

aws s3api list-object-versions \
  --bucket audit-ledger-example \
  --prefix records/2026/

aws s3api get-object-retention \
  --bucket audit-ledger-example \
  --key records/2026/event-0001.json \
  --version-id EXAMPLE_VERSION_ID

aws s3api get-object-legal-hold \
  --bucket audit-ledger-example \
  --key records/2026/event-0001.json \
  --version-id EXAMPLE_VERSION_ID
~~~

These commands only observe state and never remove retention. Replace `EXAMPLE_VERSION_ID` with a real version ID; a single key can hold multiple versions with **different retention dates and Legal Hold states**. If an API returns `AccessDenied`, check permissions/paths/policies rather than assuming the bucket lacks Object Lock.

## 5. S3 Inventory: Scheduled Object and Attribute Listings

**S3 Inventory** generates scheduled reports of objects in a **general purpose bucket**. It is far more efficient for auditing millions of objects at the key level than repeatedly calling `ListObjectsV2` and millions of `HeadObject` APIs.

### 5.1. Selecting Scope and Format

An Inventory configuration typically defines:

| Property | Example | Design Question |
| --- | --- | --- |
| **Source bucket** | `audit-ledger-example` | Which bucket needs inventorying? |
| **Prefix filter** (optional) | `records/2026/` | Export a subset of keys or the entire bucket? |
| **Included object versions** | `Current` or `All` | Current versions only, or also noncurrent versions and delete markers? |
| **Schedule** | `Daily` or `Weekly` | How fresh must reports be? |
| **Output format** | `CSV`, `ORC`, or `Parquet` | Read manually by humans or queried with Athena? |
| **Optional fields** | Size, StorageClass, EncryptionStatus, Object Lock metadata | Which attributes answer audit questions? |
| **Destination bucket/prefix** | `inventory-audit-destination/reports/` | Who can read reports, and how long are reports kept? |

When auditing Object Lock, consider **`All` versions** and optional fields such as **`ObjectLockRetainUntilDate`**, **`ObjectLockMode`**, and **`ObjectLockLegalHoldStatus`** where supported by your Inventory format and configuration. Do not inspect only current versions if compliance covers historical versions as well.

**Inventory is a scheduled report, not a real-time query API.** The initial report can take time to appear, and recent PUT/DELETE calls are not immediately reflected in existing Inventory files. Strong read-after-write consistency on direct S3 GET/LIST **does not make Inventory snapshots real-time**.

### 5.2. Where Are Reports Delivered?

~~~text
Source bucket: audit-ledger-example
  ├── records/2026/event-0001.json
  └── records/2026/event-0002.json

Destination bucket: inventory-audit-destination
  └── reports/...
      ├── manifest.json
      └── data file(s): CSV / ORC / Parquet
~~~

Exact paths follow S3 Inventory's generated directory layout (by config ID and report date), and multiple data files may be produced—never assume exactly one data file. The **Inventory report manifest** describes the exported files; do not confuse it with a hand-crafted CSV manifest format for all Batch Operations jobs.

### 5.3. Destination Bucket Permissions and Encryption

When setting up Inventory, grant S3 permission to **write report objects to the destination bucket**, typically via a bucket policy for service principal `s3.amazonaws.com` scoped with source conditions. When encrypting reports with **SSE-KMS**, grant matching KMS permissions in the key policy. Safeguards:

- Restrict reports strictly to the designated **source bucket ARN** and **account ID** to prevent service-principal misuse.
- Restrict writes to a dedicated Inventory prefix.
- Strictly limit **read access** to reports, because Inventory files expose key names, tags/classifications, history, and retention states.
- Apply Lifecycle/retention to reports so report storage does not grow unbounded.

### 5.4. Sample Inventory Configuration JSON

The snippet below only **illustrates configuration structure** and makes no changes:

~~~json
{
  "Id": "daily-object-lock-audit",
  "IsEnabled": true,
  "IncludedObjectVersions": "All",
  "Schedule": {
    "Frequency": "Daily"
  },
  "OptionalFields": [
    "Size",
    "LastModifiedDate",
    "StorageClass",
    "ObjectLockRetainUntilDate",
    "ObjectLockMode",
    "ObjectLockLegalHoldStatus"
  ],
  "Destination": {
    "S3BucketDestination": {
      "Bucket": "arn:aws:s3:::inventory-audit-destination",
      "Format": "Parquet",
      "Prefix": "reports/object-lock/"
    }
  }
}
~~~

Applying this requires configuring destination write permissions, compatible Regions/bucket types, encryption policies, quotas, and account details. Check current documentation and CLI schemas before creating in production.

### 5.5. Inspecting Configurations via CLI (Read-Only)

~~~bash
aws s3api list-bucket-inventory-configurations \
  --bucket audit-ledger-example

aws s3api get-bucket-inventory-configuration \
  --bucket audit-ledger-example \
  --id daily-object-lock-audit
~~~

If no configuration exists, the CLI returns an empty list or error. Seeing a configuration exist **does not** prove the latest report succeeded—verify the manifest/data files in the destination bucket and check delivery timestamps.

## 6. S3 Storage Lens: Seeing Trends Across Buckets

**Amazon S3 Storage Lens** delivers centralized visibility into S3 usage and activity metrics. Instead of checking retention on individual files, administrators need to know **how much data sits in each storage class, growth trends, unprotected data, abandoned multipart uploads, or which prefixes/buckets drive cost growth**.

### 6.1. Metrics vs. Per-Object Records

| Question | Storage Lens | Inventory |
| --- | --- | --- |
| How much has storage grown across a group of buckets over time? | **Best fit** | Can be aggregated after processing reports |
| Which buckets have excessive old versions or delete markers? | Provides aggregate metrics where supported | Lists every version when set to `All` |
| Until what date is `records/x.json` retained? | Not a per-object metadata lookup tool | **Best fit** with Object Lock fields enabled |
| How many objects/bytes sit in each storage class? | Aggregate dashboards/metrics | Can be grouped from Inventory data |
| Are API/traffic patterns showing anomalies? | Activity metrics at supported tiers | Inventory does not track API request history |
| Need to select 500,000 keys for a bulk job? | Does not output per-object manifests | **Inventory can feed Batch Operations directly** |

Storage Lens provides **dashboards**, **scoped filtering**, and **metrics exports** for long-term analytics. It never modifies objects, never enables Object Lock, and does not replace CloudTrail or real-time request monitoring.

### 6.2. Commonly Useful Metrics

| Metric Group | Example Metrics / Questions |
| --- | --- |
| **Storage** | Total bytes, total objects, storage class distribution |
| **Cost optimization** | Noncurrent-version bytes, delete markers, incomplete multipart uploads, lifecycle opportunities |
| **Data protection** | Coverage of versioning, replication, encryption, and protection configs per supported metrics |
| **Activity** | Request counts and traffic/activity by enabled tier |
| **Performance/Access** | Advanced views where supported metric tiers are enabled |

Exact metrics, filters, and granularity vary between **free metrics**, **advanced metrics and recommendations**, and dashboard scope. Never assume every advanced metric is available free in every account; check the current metrics catalog and pricing.

### 6.3. Interpreting Metrics Responsibly

A dashboard showing "noncurrent version bytes surging" signals a need to investigate:

1. Which buckets generate the bulk of old versions?
2. Is a job repeatedly overwriting the same key?
3. Are current Lifecycle rules expiring noncurrent versions too late, or never?
4. Are many of those versions **locked by Object Lock** and thus intentionally non-deletable before expiration?
5. Is cost growth driven by legitimate backup/compliance retention or by misconfiguration?

Storage Lens **never decides on its own** to delete all noncurrent versions. Regulated data incurs legitimate storage costs, and Batch Operations cannot override active Compliance retention.

### 6.4. Latency and Scope

Storage Lens aggregates data **periodically**, with refresh lag before updates appear on dashboards. Never use dashboards for second-by-second anomaly detection—use CloudWatch, CloudTrail/EventBridge, or dedicated security monitoring for near-real-time alerting.

Dashboards can be scoped across accounts, Regions, buckets, and finer granularities when advanced tiers are enabled. In multi-account AWS Organizations, verify IAM, delegated administrator roles, dashboard permissions, and advanced-tier fees.

### 6.5. Inspecting Storage Lens Configurations via CLI

~~~bash
aws s3control list-storage-lens-configurations \
  --account-id 123456789012 \
  --region ap-southeast-1

aws s3control get-storage-lens-configuration \
  --account-id 123456789012 \
  --config-id org-storage-overview \
  --region ap-southeast-1
~~~

These commands use **placeholder account and config IDs** and return configuration definitions rather than dashboard metric payloads. To view actual metrics, use the Storage Lens Console or authorized metric exports.

## 7. S3 Batch Operations: Acting on Large Object Sets

**S3 Batch Operations** lets you run a **job** performing a supported action across massive lists of objects/versions. S3 reads targets from a **manifest** (or supported manifest generator), manages execution progress, and outputs a **completion report**.

Common use cases:

- Add or replace object tags across targeted objects.
- Apply **Object Lock retention** or **Legal Hold** to many versions per supported rules.
- Copy objects in bulk to another location.
- Initiate restores from archive storage classes.
- Replicate pre-existing objects via Batch Replication.
- Invoke an AWS Lambda function per object for custom transformations.

**Not every operation behaves identically**: check operation-specific docs for supported actions, version ID support, metadata overwrite behavior, and billing.

### 7.1. Job Lifecycle

~~~mermaid
flowchart TD
    S["Define goal and key/version scope"] --> M["Prepare manifest\nInventory / CSV / supported generator"]
    M --> V["Review target list\nfilters, sampling, cost, IAM"]
    V --> J["Create Job\noperation + role + report"]
    J --> C{"Confirmation required?"}
    C -->|"Yes"| REVIEW["Authorized reviewer verifies and confirms"]
    C -->|"No"| Q["Ready to run"]
    REVIEW --> Q
    Q --> RUN["Batch Operations processes each object/version"]
    RUN --> RESULT["Completion report + job summary"]
    RESULT --> CHECK["Verify via API / next Inventory\ncontrolled retries"]
~~~

**Job completion does not mean 100% of objects succeeded.** Even when a job reaches `Complete`, inspect the summary, per-object failures, failure reasons, and actual impact. Operations can be retried internally; any Lambda invoked by Batch Operations must be **idempotent**.

### 7.2. What Is a Manifest?

A manifest specifies the exact objects the job is allowed to touch. You can use:

1. A supported **S3 Inventory report**, ideal when targeting all or large filtered subsets of inventoried objects.
2. A **custom CSV manifest** containing columns for bucket, key, and **version ID** when targeting exact versions.
3. An **S3-generated manifest** using service-supported filters where available for the job type.

Sample headerless CSV rows illustrating format:

~~~csv
audit-ledger-example,records/2026/event-0001.json,EXAMPLE_VERSION_01
audit-ledger-example,records/2026/event-0002.json,EXAMPLE_VERSION_02
~~~

This is sample data, **not a ready-to-run manifest**: verify real version IDs, URL encoding of keys, API format requirements, and operation compatibility. If a job sets retention on **historical versions**, omitting version IDs can target the wrong version or fail.

A scheduled Inventory report may lag behind recent uploads or deletes. For sensitive jobs, **snapshot and approve the manifest**, sample-check targets right before running, and verify state afterward.

### 7.3. Execution Role and Job Creation Permissions

Batch Operations executes actions by assuming an **IAM role**. Its trust policy must trust service principal `batchoperations.s3.amazonaws.com`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "batchoperations.s3.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This trust policy **only lets the service assume the role**—it grants no permissions to read manifests, mutate objects, or write completion reports. Add a matching permissions policy, such as:

| Task | Permissions to Review |
| --- | --- |
| Read manifest | `s3:GetObject` on the manifest object, plus KMS permissions if SSE-KMS encrypted |
| Tag objects | `s3:PutObjectTagging` / `s3:PutObjectVersionTagging` per operation/version |
| Apply retention | `s3:PutObjectRetention` on target object versions |
| Toggle Legal Hold | `s3:PutObjectLegalHold` on target object versions |
| Copy objects | Source read, destination write, KMS, and metadata/tagging permissions |
| Write completion report | `s3:PutObject` on report prefix, plus encryption permissions if needed |

The principal **creating the job** also needs permissions such as `s3:CreateJob` and `iam:PassRole` scoped strictly to the approved execution role. Never grant `iam:PassRole` on `*`, as job creators could escalate privileges via an unintended role.

### 7.4. Completion Reports and Failure Investigation

A completion report records per-object status plus error codes/messages; depending on configuration, it logs **all tasks** or **failed tasks only**. Alongside overall job status, inspect:

- Total objects **in the manifest**, succeeded count, and failed count.
- Versions that no longer existed or changed state after the manifest snapshot.
- Tasks blocked by **Object Lock Compliance/Governance**, Legal Hold, bucket policies, or KMS.
- Transient failures needing controlled retries versus succeeded items that need no rerun.
- Business impact of partial success when part of a job fails.

CloudTrail audits **job management API calls**; auditing per-object data operations requires **CloudTrail data events** or equivalent access logs. Completion reports assist operational triage, though they do not replace organizational change-control records.

### 7.5. Inspecting Jobs via CLI (Read-Only)

~~~bash
aws s3control list-jobs \
  --account-id 123456789012 \
  --region ap-southeast-1

aws s3control describe-job \
  --account-id 123456789012 \
  --job-id EXAMPLE_JOB_ID \
  --region ap-southeast-1
~~~

Never run `create-job`, `update-job-status`, or `put-object-retention` on production datasets merely to test access. Test manifests and expected outcomes in a non-prod sandbox first before executing on production targets.

## 8. Combining All Four Features: Auditing Records Retained for 7 Years

### 8.1. Scenario

An enterprise stores electronic records in S3:

~~~text
Bucket: audit-ledger-example
Prefix: documents/year=2026/
Requirement: retain every record for 7 years, plus longer holds during disputes
Scale: millions of versions, new data arriving daily
~~~

Goal: protect all new versions, find older versions missing retention, monitor storage growth/history, and remediate **only the exact versions needing fixes**.

### 8.2. Recommended Workflow

**Step 1 — Protect new data with Object Lock.** Use a bucket with Object Lock and Versioning enabled. Obtain data-owner sign-off on mode and retention duration: consider Governance during controlled pilots with strict break-glass procedures, or Compliance when retention must never be shortened. Set default retention for new versions; disallow bypass for routine operators.

**Step 2 — Export full-version Inventory.** Configure Daily Inventory (or Weekly if acceptable) with `IncludedObjectVersions=All` and Object Lock optional fields. Deliver reports into a separate, encrypted, tightly governed report bucket with its own retention policy.

**Step 3 — Query with Athena or an analytics engine.** Filter versions under `documents/year=2026/` whose retention is missing or fails policy. Distinguish delete markers, current versions, and noncurrent versions. Base queries on the exact Inventory schema and remember it reflects a periodic snapshot.

**Step 4 — Review context with Storage Lens.** Inspect trends for total bytes, noncurrent versions, object counts, storage classes, and data-protection metrics across supported scope. Map storage cost against compliance retention windows—never treat historical versions as "junk" to delete blindly.

**Step 5 — Prepare a Batch Operations job.** Build a manifest containing **strictly the object versions needing remediation**, including exact version IDs. Sample-check targets, scope the IAM execution role strictly to approved `PutObjectRetention`/`PutObjectLegalHold` actions, require job confirmation, and enable full completion reports.

**Step 6 — Verify post-job results.** Review failure counts, blocked versions, and actual applied retention. Validate final accuracy directly via Object Lock APIs on a sample or full verification set, then confirm in the next Inventory cycle.

### 8.3. Why Not Run a Blind "Retain 7 Years" Job Across Every Object?

Retention must be **calculated per record**: older objects may expire sooner, versions already in Compliance mode cannot be shortened, and disputed records under Legal Hold follow separate rules. Running an unreviewed manifest could accidentally lock data incorrectly for years with no way to undo it.

Additionally, because jobs run asynchronously, bucket state can shift after Inventory generation. Always review and approve the **exact list of version IDs** and verify before/after states.

## 9. Layered Security and Risk Controls

| Risk | Mitigation |
| --- | --- |
| Routine operators hold overly broad Governance bypass | Isolate break-glass role; restrict `s3:BypassGovernanceRetention` and alert on policy edits |
| Setting overly long Compliance retention | Pilot in a lab bucket, verify legal rules, and require formal approval before writing |
| Assuming Object Lock blocks all PUTs to the same key | Track version IDs, maintain catalog metadata, and understand current versions can advance |
| Inventory leaks sensitive key names/paths | Keep report bucket private with strict IAM, encryption, and report lifecycle limits |
| Treating Inventory as real-time state | Verify live state via direct S3 APIs or wait for the next scheduled Inventory |
| Treating Storage Lens as per-request auditing | Enable CloudTrail data events / CloudWatch / access logging as required |
| Batch job accidentally mutates the whole bucket | Require version IDs in manifest, sample-check, test in sandbox, enforce job confirmation |
| Batch execution role can delete/write any object | Scope IAM by ARN/prefix, exact action, and narrow `iam:PassRole` |
| Partial job failure | Inspect completion report, run idempotent retries on failed subset, reconcile afterward |
| Rising cost from noncurrent versions | Align Lifecycle with compliance rules, analyze via Storage Lens/Inventory, never expire early |

### 9.1. Data and Encryption Keys

A version protected by Object Lock becomes **unreadable if its KMS key becomes unusable**. With SSE-KMS, manage IAM/KMS key policies, rotation, and key-deletion safeguards carefully. Object Lock does not back up KMS keys or manage object read permissions.

When using **cross-Region replication** with Object Lock buckets, verify Object Lock compatibility at the destination, replication of retention/legal-hold metadata, and replication role permissions. Replication incurs asynchronous lag; never assume replicas exist immediately after a source PUT succeeds.

### 9.2. Costs and Budget Governance

| Component | Cost Drivers to Evaluate |
| --- | --- |
| **Object Lock** | Data cannot be deleted early → longer version retention increases storage charges |
| **Inventory** | Report generation per object scale/frequency, output storage, and querying costs |
| **Storage Lens** | Advanced metrics/features incur fees, plus metric export storage |
| **Batch Operations** | Per-job fee, per-object processed fee, and underlying S3/KMS API operation costs |
| **S3 Versioning** | Noncurrent versions, delete markers, and applicable storage classes |
| **KMS / logs / replication** | KMS API calls, logs, data transfer, replication requests, and replica storage |

No single fixed price applies across all Regions and accounts. Estimate based on object/version counts, Inventory frequency, Batch jobs, bytes, API calls, retention lengths, and current AWS pricing. Pair **AWS Budgets** and Cost Explorer reports to catch anomalies.

## 10. Distinguishing "Reports," "Metrics," and "Data Changes"

Quick tool selector by question:

~~~text
Need to prevent deleting/overwriting a version until a set date?
    -> S3 Object Lock

Need an exported catalog of versions + metadata at an inventory point?
    -> S3 Inventory

Need to compare storage/activity trends across buckets and accounts?
    -> S3 Storage Lens

Need to apply tags/retention, copy, or process millions of objects?
    -> S3 Batch Operations + manifest + execution role + completion report
~~~

At scale, they work together: **Inventory identifies candidates**, **Storage Lens sets targets and tracks trends**, **Batch Operations executes remediation**, and **Object Lock enforces immutability**. Investigation still requires CloudTrail and operational monitoring.

## 11. Safe Hands-On Practice: Read-Only Inspection and Planning

This exercise **creates, modifies, or deletes zero objects**, letting learners inspect state before proposing a Batch job. Replace placeholders with real buckets/accounts/configs/jobs you are authorized to read.

### 11.1. Inspect Object Lock and Versions

~~~bash
aws sts get-caller-identity

aws s3api get-object-lock-configuration \
  --bucket audit-ledger-example

aws s3api list-object-versions \
  --bucket audit-ledger-example \
  --prefix records/2026/ \
  --max-items 20
~~~

When using `--max-items` in the AWS CLI, inspect the pagination token to see if more items remain—never conclude the bucket holds only 20 versions. For a specific key, call `get-object-retention` and `get-object-legal-hold` with the exact version ID as shown in section 4.

### 11.2. Inspect Inventory and Storage Lens

~~~bash
aws s3api list-bucket-inventory-configurations \
  --bucket audit-ledger-example

aws s3control list-storage-lens-configurations \
  --account-id 123456789012 \
  --region ap-southeast-1
~~~

If Inventory reports already exist, view the manifest in the destination bucket via the Console or an authorized analytics tool. Inspect at least: key, version ID, `isLatest`, size, storage class, retention mode/date, and legal hold (if included in the report).

### 11.3. Draft a Job Plan Without Executing

Create a **design sheet** covering:

| Check Item | Details Required Before Approval |
| --- | --- |
| Source bucket and prefix | Real bucket name, account, Region, and data classification |
| Version list | Inventory manifest + report timestamp + sample verification |
| Operation | E.g., `PutObjectRetention`, mode, retain-until date, edge cases |
| Execution role | ARN, trust policy, object, manifest, report, and KMS permissions |
| Scale estimate | Version count, job/operation fees, and ongoing retention storage impact |
| Completion report | Destination bucket/prefix, all tasks vs. errors only, report retention |
| Post-run verification | Verification APIs, sample checks, error handling, and completion criteria |

For Compliance retention actions, **never** test creating jobs on mock production data without approved expiration dates and scope. Practice the operational workflow first with a harmless job in an isolated lab bucket.

## 12. Reinforcement Exercises

### Exercise 1 — Governance or Compliance?

One team stores internal records for 180 days and needs a strictly approved break-glass path to fix errors. Another team stores regulated records where no one may shorten the 7-year retention.

**Hint:** the first team can evaluate **Governance mode** with tightly restricted bypass permissions; the second should consider **Compliance mode** after confirming legal mandates. Both must plan post-retention lifecycle, encryption, versioning, and backups.

### Exercise 2 — DELETE Succeeded, Yet a Version Is Still Retained?

A key has version `v1` locked until next year. An admin calls `DELETE` on the key **without specifying a version ID** and receives success. Explain why `GET` on the current key returns nothing while `GET` with `versionId=v1` still succeeds.

**Hint:** `DELETE` without a version ID inserted a **delete marker**; it did not permanently delete `v1` protected by Object Lock.

### Exercise 3 — Inventory and Data Consistency

You upload a new object at 10:00, run a direct S3 `GET` at 10:01 and see it, yet this morning's Inventory report lacks the key.

**Hint:** Inventory is a **scheduled report**, not a real-time `LIST`. That difference does not mean S3 lost strong read-after-write consistency.

### Exercise 4 — Storage Lens or Inventory?

Pick the right tool:

1. Track monthly trends of noncurrent version bytes.
2. Export version IDs and retain-until dates for 20,000 files.
3. Apply Legal Hold across 20,000 selected versions.
4. Block permanent deletion of files under active dispute.

**Answers:** (1) Storage Lens; (2) Inventory with Object Lock optional fields; (3) Batch Operations + manifest with version IDs; (4) Object Lock Legal Hold. For (3), verify final state via APIs afterward.

### Exercise 5 — Job Has a 1.5% Failure Rate

A Batch Operations job processed 100,000 objects; the completion report shows 1,500 failed tasks. Operations proposes re-running the job on the entire manifest.

**Hint:** first analyze failure causes: vanished versions, missing IAM/KMS rights, retention blocks, transient errors, or keys updated mid-run. Build a retry manifest strictly for the **failed subset** or use idempotent operations; never assume re-running all 100,000 is safe.

### Exercise 6 — Permission Design

An IAM role holds `s3:BypassGovernanceRetention` across an entire bucket plus `s3:DeleteObjectVersion`. This role is attached to a daily ETL pipeline that only needs to write new files. What is the risk?

**Hint:** the pipeline can bypass Governance retention and permanently delete protected versions if requests use the bypass mechanism; move those privileges to an isolated break-glass role and restrict ETL strictly to required keys and write actions.

## 13. Common Misconceptions

| Claim | Accurate Understanding |
| --- | --- |
| "Object Lock locks the whole key so no one can upload new versions." | Object Lock protects **specific versions**; new versions can still be written if permitted. |
| "In Governance mode, nobody can delete the version." | Principals with bypass permission sending the bypass header can override Governance. |
| "Compliance mode can be disabled with `AdministratorAccess`." | Unexpired Compliance retention cannot be bypassed by standard IAM admin privileges. |
| "Legal Hold expires automatically at `RetainUntilDate`." | Legal Hold is independent and **has no automatic expiration date**. |
| "Enabling default retention locks all existing objects." | Default retention applies primarily to **new versions**; existing objects must be remediated separately. |
| "A successful `DELETE` on a key means the locked version is gone." | `DELETE` without a version ID only creates a delete marker. |
| "Inventory is like a real-time `LIST`." | Inventory updates **periodically**, never as an instant state snapshot. |
| "Storage Lens shows each object's retain-until date on the dashboard." | Storage Lens aggregates metrics; use Inventory or APIs for per-object metadata. |
| "Batch Operations bypasses IAM, KMS, and Object Lock." | Jobs remain subject to all those controls and require a properly permissioned execution role. |
| "Job status `Complete` means 100% of objects succeeded." | Always check the **per-object completion report** and verify actual object state. |
| "Object Lock replaces backups." | You still need restore procedures, KMS key governance, Regional resilience, and DR strategies. |
| "S3 Versioning uses no extra storage." | Noncurrent versions, reports, and replicas incur additional storage charges. |

## 14. Key Takeaways

For enterprise-scale S3 governance:

1. **Object Lock** enforces **object version** immutability via retention and Legal Hold; designing modes and bypass permissions carefully is critical.
2. **S3 Inventory** provides **scheduled catalogs of objects/versions and metadata**, ideal for scoping bulk remediation while keeping snapshot lag in mind.
3. **S3 Storage Lens** delivers **aggregate metrics and usage trends** to expose cost drivers and protection gaps across buckets, accounts, and organizations.
4. **S3 Batch Operations** executes bulk actions across **manifests of objects/versions**, requiring least-privilege execution roles, confirmation gates, completion reports, and post-job verification.

Strong production architectures combine all four with **IAM, encryption, logging, replication/backups, lifecycle rules, and formal approvals**. Because a single job can modify vast numbers of versions rapidly, **strict scope protection and manifest review** must be mandatory operational gates.

### Official AWS Documentation for Further Reading

- [Using S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) — Concepts, versioning, and WORM model.
- [Object Lock retention modes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html#object-lock-retention-modes) — Governance, Compliance, and bypass mechanics.
- [Legal holds in S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html#object-lock-legal-holds) — Legal Holds independent of retention.
- [Amazon S3 Inventory](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html) — Schedules, formats, fields, and delivery lag.
- [Setting up S3 Inventory](https://docs.aws.amazon.com/AmazonS3/latest/userguide/configure-inventory.html) — Configuration and destination bucket policies.
- [Amazon S3 Storage Lens](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens.html) — Dashboards, metrics, and scope.
- [S3 Storage Lens metrics glossary](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens_metrics_glossary.html) — Metric definitions by category and tier.
- [S3 Batch Operations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops.html) — Jobs, manifests, execution roles, and reports.
- [S3 Batch Operations job manifests](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-basics.html) — Target selection and job workflows.
- [Tracking S3 Batch Operations job status](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-job-status.html) — Monitoring job results and status.
- [Security best practices for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — Access control, encryption, public access, and auditing.

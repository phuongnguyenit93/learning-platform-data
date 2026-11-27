# Autoclass and Object Lifecycle Management

> **Chapter:** Cloud Storage  
> **Module:** CLOUD_PROVIDERS_GCP

A Google Cloud system can generate millions of files: user images read frequently during the first few days, log files used only for investigations, monthly exported reports, backups that may go unread for years, and temporary data needed for only a few weeks. Keeping every object in **Standard storage** forever can drive up storage costs; moving everything to **Archive** can introduce unsuitable operation costs, access constraints, and recovery trade-offs. Cloud Storage provides two key mechanisms to automate object lifecycle governance:

- **Autoclass:** automatically determines the **storage class** based on **object data read** activity; convenient when access frequency is hard to predict.
- **Object Lifecycle Management (OLM):** executes **configured actions** when objects meet conditions such as age, name prefix, version, or a date in metadata; suitable for rule-based class transitions and **deleting expired data**.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, where learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through operational scenarios, learners learn to select services, protect resources, automate releases, and monitor reliability and cost. This lesson uses Cloud Storage examples for a Java API, data pipelines, and backups to make evidence-based decisions rather than enabling automation by guesswork.

**Learning Outcomes:** After this lesson, you will be able to:

1. Distinguish objects, buckets, storage classes, access patterns, lifecycle rules, and retention.
2. Explain how Autoclass transitions among Standard, Nearline, Coldline, and Archive; understand size thresholds and fee types.
3. Design JSON lifecycle rules for `Delete`, `SetStorageClass`, and `AbortIncompleteMultipartUpload`.
4. Choose the right mechanism based on access, retention, security, recovery, and cost requirements.
5. Identify rules that are **incompatible between Autoclass and Lifecycle Management**.
6. Enable and verify features using the Console or `gcloud storage` in a test project.
7. Troubleshoot scenarios where objects have not transitioned, have not been deleted, cannot be deleted, or cause unexpected costs.
8. Plan testing, monitoring, data protection, and rollback before applying changes in production.

## 1. Understand the Cloud Storage Model Before Configuring Automation

**Cloud Storage** is an object storage service. Data is organized into **buckets**, with **objects** inside each bucket. An object consists of data and metadata, identified by name; with versioning, **generations** can store multiple versions under the same name.

~~~text
Google Cloud project: order-platform-prod
  └── Bucket: gs://order-assets-prod
      ├── receipts/2026/11/order-123.pdf     (object)
      ├── images/products/item-456.jpg      (object)
      ├── reports/monthly/2026-10.csv       (object)
      ├── temp/exports/task-789.json        (object)
      └── backups/db/2026-11-01.dump        (object)
~~~

In a **flat namespace** bucket, `/` characters in object names are typically used as logical prefixes rather than OS directories. With a **hierarchical namespace**, Cloud Storage supports folders under its own model; when writing lifecycle rules, you still must read exact prefix-matching rules and data scope carefully.

### 1.1. Bucket Location Is Different from Object Storage Class

| Property | Example | Meaning |
| --- | --- | --- |
| **Bucket location** | `asia-southeast1`, dual-region, or multi-region | Where data is stored per regional selection |
| **Object storage class** | Standard, Nearline, Coldline, Archive | Pricing model and access/storage characteristics |
| **Default storage class** | Standard | Default storage class for new objects when none is specified |
| **Retention policy** | Retain at least 365 days | Prevents premature deletion/overwrite until conditions are met |
| **Soft delete policy** | Retains deleted items for an additional window | Recovery mechanism after deletion |
| **Object Versioning** | Retains overwritten/deleted generations | Supports restoring prior versions |
| **Autoclass** | Enabled, terminal storage class | Service automatically changes class based on access |
| **Lifecycle configuration** | One or more rules | Service executes actions when conditions match |

Moving an object from Standard to Nearline **does not move the bucket to another region**. Reducing storage cost by changing class also does not change IAM permissions, VPC Service Controls, encryption keys, or the bucket's public access settings.

### 1.2. Common Storage Classes

| Storage Class | Typical Intended Use | Minimum Storage Duration When **Manually Managed** | Retrieval Fee Under Standard Pricing |
| --- | --- | --- | --- |
| **Standard** | Frequent reads, active applications | None | No |
| **Nearline** | Infrequent reads, e.g., less than once a month | 30 days | Yes |
| **Coldline** | Colder data, expected to be read very rarely | 90 days | Yes |
| **Archive** | Long-term archival data, rarely restored | 365 days | Yes |

Cloud Storage also offers other capabilities/storage tiers such as **Rapid storage** in specific bucket models. However, the Autoclass progression covered in this lesson applies to Standard, Nearline, Coldline, and Archive.

**Note:** Cloud Storage Archive does not mean opening a multi-hour restore request like some tape-based systems. Objects remain accessible online via the service; request/retrieval fees and minimum storage duration are the factors to calculate—aside from waivers specific to Autoclass.

## 2. Two Forms of Automation: Similarities and Differences

~~~mermaid
flowchart TB
  BUCKET["Cloud Storage bucket"] --> A{"Choose strategy"}
  A --> AUTO["Autoclass\nBased on object data access history"]
  A --> LC["Object Lifecycle Management\nBased on action + condition"]
  AUTO --> COST["Optimizes class, promotes back to Standard on read"]
  LC --> DELETE["Delete after expiration or delete old versions"]
  LC --> TRANS["SetStorageClass when Autoclass is disabled"]
  AUTO -. "Can be combined with Delete rules" .-> DELETE
~~~

| Criterion | Autoclass | Object Lifecycle Management |
| --- | --- | --- |
| Configuration scope | **Entire bucket** | Bucket-level rules applied to matching objects |
| Decision basis | **Data reads** of objects; system tracks access level | `age`, `isLive`, `matchesPrefix`, `customTime`, class, etc. |
| Changing storage class | **Automatic** along Google's transition path | **Rule-based** via declared `SetStorageClass` |
| Auto-promote read objects to Standard | **Yes**, per Autoclass rules | Not a default lifecycle behavior |
| Deleting expired objects | **No** | **Yes** via `Delete` |
| Cleaning up incomplete multipart uploads | Not an Autoclass function | **Yes** via `AbortIncompleteMultipartUpload` |
| Managing classes by different prefixes | No: logic applies bucket-wide, with size exclusions | Yes, rules can filter with `matchesPrefix` |
| Need to forecast access patterns | Less necessary | Need to design appropriate timelines and conditions |
| Notable costs | Management fee, enablement charge, operations, storage | Transition operations, minimum duration/early deletion on delete, storage |
| Used together in one bucket? | **With limits:** allows certain lifecycle actions | **Cannot use** `SetStorageClass` or `matchesStorageClass` when Autoclass is enabled |

**Key Decision Point:** Autoclass and Lifecycle Management **are not two names for the same feature**. Autoclass optimizes storage class based on access, while lifecycle handles lifecycle rules such as *"delete temporary files after 30 days"* or *"delete noncurrent versions after 90 days."*

### 2.1. Data Classification Examples

- New product images read heavily while older images may occasionally be viewed again: **Autoclass** is worth evaluating.
- Accounting report files that must be kept exactly 7 years and deleted per policy: use **retention** plus **Lifecycle Delete**, do not rely on Autoclass.
- Backups guaranteed not to be read for 12 months with a fixed retention period: **static storage class + lifecycle** may beat Autoclass management fees.
- Daily temporary files with a fixed 14-day lifetime: **Lifecycle Delete by prefix/age**, no Autoclass needed.
- Objects with both uncertain access patterns and an expiration policy: **Autoclass + Delete lifecycle** (without `SetStorageClass`/`matchesStorageClass`).

## 3. How Does Autoclass Work?

**Autoclass** is a **bucket-level** configuration that monitors **data reads** on each object. When enabled, Google Cloud automatically adjusts an object's class based on periods of inactivity; when the data is read again, the object can transition back to **Standard**.

Key principles:

1. **All new objects start in Standard**, even if the upload request attempts to specify a different class.
2. **The bucket's default storage class must be Standard** when Autoclass is enabled; attempts to change the default class to another tier will fail.
3. Objects **smaller than 128 KiB** stay in Standard and **do not** transition to colder classes; the size threshold measures **object data**, excluding metadata.
4. Objects **at least 128 KiB** can transition to Nearline/Coldline/Archive over periods without reads.
5. Accessing **data** via supported methods can promote an object back to Standard; **viewing or editing metadata alone** does not warm the data.
6. Class transitions are **asynchronous**; do not expect class metadata to change at the exact second an object becomes eligible.
7. **Soft-deleted objects** do not continue transitioning storage classes under Autoclass during the soft-delete retention window; restoring a soft-deleted object creates the object in Standard.

### 3.1. What Is the Terminal Storage Class?

The **terminal storage class** is the coldest class to which Autoclass is permitted to transition an object after prolonged inactivity.

- **NEARLINE:** the **default**. Objects unread for 30 days can move from Standard to Nearline; they will not move down to Coldline or Archive.
- **ARCHIVE:** option allowing objects to progress from Standard → Nearline → Coldline → Archive if they remain unread long enough.

**There is no `COLDLINE` terminal option** in current Autoclass settings; only `NEARLINE` or `ARCHIVE` exist. If you need a custom schedule like "Coldline from day 180, never Archive," use Lifecycle Management on a bucket **without Autoclass** or separate buckets.

### 3.2. Timeline When Terminal Class Is NEARLINE

~~~text
Object >= 128 KiB uploaded / data just read
      |
      v
STANDARD
      |
      | 30 days without reads
      v
NEARLINE <---- terminal, stays here until next data read
      |
      | Successful GET of object data
      v
STANDARD, starts a new 30-day cycle
~~~

Example for a file `images/products/seasonal.jpg`:

- Day 0: uploaded to Standard.
- No data access for 30 days: eligible to move to Nearline.
- Day 45: application GETs file content: object moves back to Standard.
- If unread for another 30 days: becomes eligible to move to Nearline again.

Day counts are **eligibility thresholds**, not minute-accurate execution schedules. Viewing metadata in the Console does not necessarily reset the inactivity timer.

### 3.3. Timeline When Terminal Class Is ARCHIVE

~~~mermaid
flowchart LR
    STD["Standard\nRight after upload/GET"] -->|"Unread 30 days"| NEAR["Nearline"]
    NEAR -->|"Unread through day 90"| COLD["Coldline"]
    COLD -->|"Unread through day 365"| ARCH["Archive"]
    NEAR -. "Data GET" .-> STD
    COLD -. "Data GET" .-> STD
    ARCH -. "Data GET" .-> STD
~~~

| Unread Milestone | Target Class If Eligible | Notes |
| --- | --- | --- |
| Under 30 days | Standard | Newly uploaded or recently read object |
| From 30 days | Nearline | First colder step |
| From 90 days | Coldline | Total unread duration from cycle start |
| From 365 days | Archive | Only when `terminal=ARCHIVE` |

**Do not add the milestones as 30 + 90 + 365 days.** The 90-day mark already includes 30 days in Standard plus 60 days in Nearline; the 365-day mark includes 30 Standard + 60 Nearline + 275 Coldline.

### 3.4. What Counts as Data Access?

According to Google Cloud, the last-read timestamp used in Autoclass decisions updates when an object is accessed via a **GET object** under supported semantics. Operations such as **COPY** or **REWRITE**, as well as reading/modifying metadata, do not update the timestamp in the same way.

Implications:

- A batch job that routinely **GETs all images** for scanning, training, or analytics can keep most data in Standard → Autoclass saves little.
- A process that only **lists or reads metadata** does not necessarily warm objects.
- Moving or copying objects in a pipeline should not be used as an experiment assuming it reliably resets last-access time.
- With Cloud Storage FUSE, CDN caches, and proxies, measure **actual GETs reaching Cloud Storage**; a cache hit at another layer does not necessarily issue a GET to the origin object.

To understand costs, do not look only at how often users open the app; trace **every data flow that touches the object**.

### 3.5. Object Size and Exclusion Chart

| Object Size | Does Autoclass Transition to Colder Classes? | Explanation |
| --- | --- | --- |
| 16 KiB | No | Smaller than 128 KiB, stays Standard |
| 127 KiB | No | Smaller than 128 KiB |
| 128 KiB | Yes | Meets threshold |
| 4 MiB | Yes | Transitions based on GET history |
| 5 GiB | Yes | Evaluate access/cost balance |

A bucket holding **millions of few-KiB objects** may gain little from Autoclass: those objects will never transition, though their storage still incurs charges. Alternatives include **safely batching data**, Lifecycle Delete on expiration, or choosing a pipeline-appropriate storage format—without blindly merging objects if individual access is required.

## 4. Enabling Autoclass for New and Existing Buckets

### 4.1. IAM and Security Prerequisites

Current setup documentation lists these permissions:

- `storage.buckets.get`.
- `storage.buckets.update` to modify bucket configuration.
- `storage.buckets.list` when using the Console to list buckets.

The recommended role is `roles/storage.admin` **on the specific bucket**, or a custom role with the least required permissions. Do not use Project Owner/Editor just to bypass permission errors; someone with object read permissions does not automatically have permission to enable Autoclass.

Before enabling in production:

1. Export/back up bucket metadata and existing lifecycle configuration.
2. Check for `SetStorageClass` or `matchesStorageClass`; resolve compatibility **before** enabling.
3. Estimate the **one-time enablement charge** and impact on all existing objects.
4. Check retention/soft delete/versioning, encryption rules, and auditing.
5. Audit pipelines that routinely GET data, including backup scanners or DLP.
6. Capture a baseline report of costs and bytes per storage class.

### 4.2. Console for a New Bucket

1. Open [Cloud Storage → Buckets](https://console.cloud.google.com/storage/browser).
2. Click **Create bucket** in an authorized project and enter a globally unique bucket name.
3. Choose a bucket location matching residency/latency needs.
4. Under **Default storage class**, select **Autoclass** per the current UI.
5. Choose **included classes / terminal class**: Nearline (default) or Archive.
6. Set **Uniform bucket-level access**, **Public access prevention**, soft delete, encryption, and retention per policy.
7. Review settings and create the bucket.
8. Open the **Configuration** tab to verify **Managed with Autoclass** status and included classes.

When creating a new empty bucket, there are no existing objects, so there is no enablement charge on legacy data as happens when enabling on a populated bucket; object storage and Autoclass management fees still apply during usage.

### 4.3. CLI: Inspect Configuration Before Changing

Read-only commands:

~~~bash
gcloud config get-value project

gcloud storage buckets describe gs://BUCKET_NAME \
  --format="yaml(name,location,storageClass,autoclass,lifecycle,softDeletePolicy,versioning)"

gcloud storage ls gs://BUCKET_NAME/
~~~

To enable Autoclass on an approved test bucket:

~~~bash
# MUTATING bucket: check costs and lifecycle before running
gcloud storage buckets update gs://BUCKET_NAME \
  --default-storage-class=STANDARD \
  --enable-autoclass \
  --autoclass-terminal-storage-class=NEARLINE
~~~

If you want to allow Archive in a **test** bucket (after weighing costs), use:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --enable-autoclass \
  --autoclass-terminal-storage-class=ARCHIVE
~~~

Depending on the SDK version, enabling Autoclass on a bucket whose default class is not Standard may require **passing `--default-storage-class=STANDARD` in the same command**. Check `gcloud storage buckets update --help` and verify the actual state afterward.

Check status:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(autoclass)"
~~~

**Permission/change notice:** The `update` command modifies a real bucket and can alter existing objects' classes. Never run it on shared or production buckets without an impact assessment, rollback plan, and approval.

### 4.4. Enabling Autoclass on a Bucket with Existing Data

When you **enable Autoclass on an existing bucket**:

- Non-soft-deleted objects are transitioned back to **Standard**, though class metadata may not reflect Standard immediately.
- Objects already in Standard also restart a new **30-day** unread cycle.
- There is a **one-time enablement charge**, which can include retrieval and early deletion fees on existing data plus Class A operations depending on objects/classes.
- The configuration can take up to **one day** to take effect; some jobs may continue operating under prior settings during this window.

Example: A bucket holding 50 TB of Archive with millions of rarely read objects can incur **significant charges** when enabling Autoclass because objects must move back to Standard to begin management. Never assume "enabling Autoclass to save money immediately" is a free operation.

### 4.5. Changing Terminal Class and Disabling Autoclass

- If changing `ARCHIVE → NEARLINE`, objects currently in Coldline/Archive may be transitioned up to Nearline per rules.
- If changing `NEARLINE → ARCHIVE`, objects currently in Nearline are treated as having just moved to Nearline and need another **60 unread days** before becoming eligible for Coldline.
- When **disabling Autoclass**, each object **retains its current storage class**. It does not automatically revert to Standard.
- After disabling, you must **wait at least one day** before re-enabling Autoclass on the same bucket.
- Configuration changes can take up to one day to complete.

Example disable command (mutating):

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --no-enable-autoclass
~~~

**Risk:** Disabling Autoclass while many objects remain in Archive subjects future reads to standard Archive pricing (retrieval/minimum duration depending on circumstances), losing Autoclass fee waivers. Calculate transition costs and manual class policies before disabling.

## 5. Autoclass Costs: Charges You Must Not Overlook

Autoclass optimizes storage costs, but **it is not free**. Track these cost lines separately:

| Component | When It Applies | How to Understand It |
| --- | --- | --- |
| Storage at rest | Objects residing in each storage class | Priced by location/class and Autoclass-specific SKUs |
| **Autoclass management fee** | Eligible objects (at least 128 KiB) in an Autoclass bucket | Billed per object count and managed duration |
| **One-time enablement charge** | Enabling on a bucket with existing objects | May include retrieval, early deletion, and Class A |
| GET/PUT/LIST and other operations | Application calls to Cloud Storage | Charged at Standard operation rates under Autoclass |
| Transition to colder classes | Autoclass transitions automatically | No transition operation charge |
| Nearline → Standard on read | When Autoclass warms an object | No Class A transition charge for this path |
| Coldline/Archive → Standard or Nearline | When Autoclass promotes to a warmer class | Class A transition operation applies per documentation |
| Data transfer/egress | Access across regions/networks | Network fees still apply per pricing |
| Soft delete, versioning, replication | If enabled | Increases stored bytes/objects and associated fees |

### 5.1. Autoclass and Retrieval/Early Deletion Fees

While **using Autoclass**:

- Google Cloud **does not charge standard cold-class retrieval fees**, **except what may be part of the one-time enablement charge**.
- Google Cloud **does not charge cold-class early deletion fees** during Autoclass usage, **except within the enablement charge**.
- Operations are billed at Standard operation rates, though promotions from Coldline/Archive incur a Class A transition charge.
- **Do not confuse** "no retrieval fee" with "reads are completely free": requests, billable class transitions, network egress, and downstream services still generate costs.

### 5.2. Evaluate Break-Even Instead of Looking Only at Price/GB

A modeling formula:

~~~text
TCO_Autoclass ≈
    SUM(bytes-at-rest by class/location × corresponding class price)
  + management fee by eligible object-duration
  + enablement charge (if newly enabled on existing data)
  + applicable operations / transition operations
  + network egress / replication / soft-delete
  + operational overhead

TCO_Lifecycle ≈
    SUM(bytes-at-rest by class/location × class price)
  + Class A operations from SetStorageClass
  + retrieval/early-deletion fees per class and usage
  + operations / network / soft-delete / replication
  + managing and testing lifecycle rules
~~~

For example, a bucket with **1 million small 32 KiB objects** read daily: most objects are never moved to colder classes by Autoclass, so significant Autoclass savings are unlikely. Conversely, a bucket of large objects with unpredictable hot/cold cycles can reduce storage costs via Autoclass.

**Never hard-code a generic savings figure like "30%"** across all workloads. Build a TCO spreadsheet using current Cloud Storage pricing for the actual location, object counts by size, GET frequency, egress volume, and retention duration.

### 5.3. Cost Fluctuations with Manual Cold Classes

Without Autoclass, Nearline, Coldline, and Archive carry **minimum storage durations** of **30, 90, and 365 days**, respectively. Deleting, replacing, or moving objects early can trigger an **early deletion charge**. With Object Lifecycle Management, **`SetStorageClass` does not incur an early deletion charge** for rule-driven transitions, though it incurs a **Class A operation charge**. When a Delete rule removes an object from a cold class before its minimum duration per billing rules, early deletion may apply. See the Lifecycle section below for details.

## 6. Object Lifecycle Management: Action + Condition

**Object Lifecycle Management** lets you attach **a set of rules to a bucket**. Each rule has:

- **Action:** what Cloud Storage does to matching objects.
- **Conditions:** criteria that must be satisfied for the action to run.

Example policy:

~~~text
When an object under prefix temp/ reaches 30 days since creation:
    → Delete

When a report object reaches 90 days since creation:
    → SetStorageClass COLDLINE  (only on buckets WITHOUT Autoclass)

When a noncurrent version has existed for 60 days:
    → Delete that version
~~~

### 6.1. Boolean Logic and Precedence

- **Within one rule:** all conditions must be true (**AND**).
- **Multiple rules with the same action:** the action can run if any matching rule is satisfied (**OR** across rules).
- If multiple rules with different actions match the same object, Cloud Storage **executes only one action** according to precedence—for example, **Delete takes precedence over SetStorageClass**.
- When multiple `SetStorageClass` rules match, the rule transitioning to the class with the lowest at-rest storage price takes precedence per documentation.
- Actions **do not run at the exact instant a condition becomes true**. Cloud Storage scans and executes **asynchronously**.

~~~mermaid
flowchart TD
    OBJ["Object and metadata"] --> MATCH{"One or more rules match?"}
    MATCH -- "No" --> STAY["Unchanged"]
    MATCH -- "Yes" --> CONFLICT{"Multiple conflicting actions?"}
    CONFLICT -- "Includes Delete" --> DEL["Delete if retention/hold allows"]
    CONFLICT -- "Only SetStorageClass" --> TRANS["Select class per precedence rules"]
    CONFLICT -- "Single action" --> ACT["Execute matching action"]
    DEL --> PROTECT["Soft delete / Versioning may retain data"]
~~~

### 6.2. Three Lifecycle Actions

| Action | Purpose | Special Conditions |
| --- | --- | --- |
| **Delete** | Deletes objects upon expiration; can target live/noncurrent versions | Blocked while retention policies/object holds remain active |
| **SetStorageClass** | Transitions objects to a supported colder class | **Cannot be used when Autoclass is enabled**; incurs Class A fee per transition |
| **AbortIncompleteMultipartUpload** | Aborts incomplete XML API multipart uploads | Only supports `age`, `matchesPrefix`, and `matchesSuffix` as conditions |

Object Lifecycle Management **does not support arbitrary actions** like sending emails, compressing files, invoking Cloud Run, or moving objects to another bucket. For complex workflows, use event-driven processing/Cloud Run/Workflows or Storage Batch Operations where supported, with proper IAM and error handling.

### 6.3. Common Lifecycle Conditions

| JSON Condition | How It Matches | Example |
| --- | --- | --- |
| `age` | Days since **object creation / upload completion** | `"age": 30` |
| `createdBefore` | Objects created before a specified UTC date | `"createdBefore": "2026-01-01"` |
| `isLive` | Whether the generation is the current live version | `"isLive": false` |
| `daysSinceNoncurrentTime` | Days after a generation became noncurrent | `"daysSinceNoncurrentTime": 60` |
| `numNewerVersions` | At least N newer generations exist | `"numNewerVersions": 3` |
| `matchesPrefix` | Object name starts with one of the prefixes (case-sensitive) | `"matchesPrefix": ["temp/"]` |
| `matchesSuffix` | Object name ends with one of the suffixes | `"matchesSuffix": [".log", ".tmp"]` |
| `matchesStorageClass` | Object currently belongs to one of the listed classes | **Cannot be used with Autoclass** |
| `daysSinceCustomTime` | Days since `Custom-Time` metadata | Used when apps set a business timestamp |
| `customTimeBefore` | Custom-Time is before a specified date | Retain data by business milestones |
| `sizeAboveBytes`/`sizeBelowBytes` | Filter by size in bytes | Prevent class transitions on too many tiny objects |

**Different types of "age":**

- `age` uses **object creation time**; it **does not** measure from the last GET and **does not** reset when changing storage class or becoming noncurrent.
- `daysSinceNoncurrentTime` measures from when an object generation was replaced/deleted and became **noncurrent**; meaningful only with versioning.
- `daysSinceCustomTime` uses **Custom-Time metadata** set by the application.
- **Autoclass**, by contrast, uses **data read activity**, not the three age conditions above.

### 6.4. Prefix Is the Object Name, Not the Full Path

Example object:

~~~text
gs://company-audit-data/temp/reports/job-123.csv
~~~

To match the prefix, declare:

~~~json
"matchesPrefix": ["temp/reports/"]
~~~

Do not write `"gs://company-audit-data/temp/reports/"` or prepend a leading `/` to the object name. Prefix matching is **case-sensitive**, so `Temp/` and `temp/` are two different values.

## 7. Basic Lifecycle JSON and Autoclass Compatibility

### 7.1. Delete Temporary Files After 30 Days

This rule is compatible with **both Standard buckets and Autoclass buckets**:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"],
        "isLive": true
      }
    }
  ]
}
~~~

**Explanation:** Only live objects whose names start with `temp/` and were created **at least 30 days ago** qualify for Delete. No class check is needed because the goal is deleting expired items **regardless of whether Autoclass transitioned them**.

**Versioning warning:** With Object Versioning enabled, deleting a live generation turns that generation into a noncurrent version. A rule with only `isLive:true` **does not delete noncurrent generations**, so total storage can keep growing. Add a separate rule to clean up old versions according to an agreed retention period.

### 7.2. Combining Delete and Noncurrent Version Cleanup

With Object Versioning enabled, suppose you want:

- Live objects under `temp/` deleted at 30 days old.
- Noncurrent generations under `temp/` deleted 14 days after becoming noncurrent.

You can use:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"],
        "isLive": true
      }
    },
    {
      "action": { "type": "Delete" },
      "condition": {
        "daysSinceNoncurrentTime": 14,
        "matchesPrefix": ["temp/"],
        "isLive": false
      }
    }
  ]
}
~~~

**Operational constraint:** The 30/14-day thresholds are illustrative for **non-critical lab data**. For reports or backups, base retention periods on legal compliance, recovery SLAs, and backup policies—never delete old versions merely to trim storage bills.

### 7.3. Age-Based Class Transition Rule — Only for NON-Autoclass Buckets

When you know reports do not need frequent reads after 90 days, you can automate transitions:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesPrefix": ["reports/monthly/"],
        "sizeAboveBytes": 131072
      }
    }
  ]
}
~~~

Use only on **buckets without Autoclass**. If Autoclass is enabled, this rule is **invalid**. Add a separate Delete rule when deletion is needed, accounting for retention and early deletion.

**Why include `sizeAboveBytes`?** Changing storage class via lifecycle generates a **Class A operation** per object. With millions of small objects, operation fees can exceed storage savings. This condition is an example filtering objects larger than 128 KiB; tune the threshold using your actual cost model.

### 7.4. Cleaning Up Incomplete Multipart Uploads

~~~json
{
  "rule": [
    {
      "action": { "type": "AbortIncompleteMultipartUpload" },
      "condition": {
        "age": 7,
        "matchesPrefix": ["uploads/"]
      }
    }
  ]
}
~~~

This rule applies only to **incomplete XML API multipart uploads**—it does not mean "delete all objects in `uploads/` after 7 days." Do not use conditions other than `age`, `matchesPrefix`, and `matchesSuffix` for this action.

### 7.5. Autoclass Bucket + Delete + Abort

A **compatible** configuration:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 60,
        "matchesPrefix": ["temporary/"]
      }
    },
    {
      "action": { "type": "AbortIncompleteMultipartUpload" },
      "condition": {
        "age": 7
      }
    }
  ]
}
~~~

There is no `SetStorageClass` or `matchesStorageClass`, so it can run alongside Autoclass **provided no other policies conflict**. The Delete rule remains subject to Object Versioning, soft delete, object holds, and retention.

### 7.6. Configurations INVALID with Autoclass

Two examples that **cannot be combined with Autoclass**:

~~~json
{
  "rule": [
    {
      "action": { "type": "SetStorageClass", "storageClass": "ARCHIVE" },
      "condition": { "age": 365 }
    }
  ]
}
~~~

Or:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 365,
        "matchesStorageClass": ["NEARLINE"]
      }
    }
  ]
}
~~~

**The second case is easy to miss:** Even when the action is Delete, the `matchesStorageClass` condition **is still prohibited** with Autoclass. If the goal is age-based deletion, use `age`, `matchesPrefix`, `isLive`, or Custom-Time instead of depending on a storage class managed by Autoclass.

## 8. Rule Precedence and Surprising Behaviors

### 8.1. Multiple Actions Matching Together

A Standard bucket without Autoclass has two rules:

~~~json
{
  "rule": [
    {
      "action": { "type": "SetStorageClass", "storageClass": "COLDLINE" },
      "condition": { "age": 60 }
    },
    {
      "action": { "type": "Delete" },
      "condition": { "age": 60 }
    }
  ]
}
~~~

When an object reaches 60 days, **Delete takes precedence over SetStorageClass**. Do not expect the object to transition class and then be deleted in the same pass. To retain objects until at least day 180, set `SetStorageClass` at `age=60` and `Delete` at `age=180`, after checking class minimum durations.

### 8.2. All Conditions in a Rule Are ANDed

Example:

~~~json
"condition": {
  "age": 90,
  "matchesPrefix": ["reports/"],
  "isLive": false
}
~~~

This means the object must be **at least 90 days old since creation**, **start with `reports/`**, and currently be a **noncurrent version**. If you meant "90 days since being overwritten," replace `age` with `daysSinceNoncurrentTime`.

### 8.3. Eligibility Day Is Not Guaranteed Execution Day

An object created at 10:00 UTC on Jan 01 becomes eligible for `age=30` at 10:00 UTC on Jan 31. However, Cloud Storage executes lifecycle **asynchronously**. Data may persist for some time past that threshold.

**Do not design business logic assuming "objects will vanish at exactly 00:00 on expiration day."** If an application requires deadline-exact deletion, implement an active workflow and compliance verification; lifecycle is a useful background tool, not a "delete to the exact second" SLA.

### 8.4. Editing Rules Does Not Instantly Cancel Old Rules

After updating a lifecycle configuration, Google Cloud may continue executing the previous rules for up to roughly **24 hours**. For example, if you raise `age:10` to `age:20`, an 11-day-old object **can still be deleted** during the propagation window. Therefore:

- Do not deploy aggressive delete rules thinking you can "quickly fix them if anything looks wrong."
- Test on a lab bucket or small prefix first.
- Do not treat deleting/updating a rule as a guaranteed rollback that preserves every object.
- Enable soft delete/versioning or snapshots/backups matching your RPO to reduce risk.

## 9. Deploying Object Lifecycle Management via Console and CLI

### 9.1. Permissions and Preflight Checks

Typically required permissions: `storage.buckets.get` and `storage.buckets.update` (the Console usually also needs `storage.buckets.list`). `roles/storage.admin` on the bucket includes these permissions, or you can use a custom role.

Before updating:

1. Verify bucket/project/location and confirm **you own the target bucket**.
2. Read existing lifecycle rules, soft delete, versioning, retention, and holds.
3. If Autoclass is enabled, verify there is **no** `SetStorageClass` or `matchesStorageClass`.
4. Prepare JSON containing **all rules** you want to keep, not just the new rule.
5. Obtain approval for Delete actions and deletion ages from the data owner.
6. Check Class A operation costs and recovery options.

### 9.2. Console

1. Open [Cloud Storage → Buckets](https://console.cloud.google.com/storage/browser).
2. Select the bucket and open the **Lifecycle** tab.
3. Click **Add rule**, choose an action (Delete, SetStorageClass, Abort incomplete multipart upload as supported by the UI).
4. Define conditions: age, prefix, live version, or relevant fields.
5. Review the full rule list, precedence, and potential conflicts.
6. Save and **re-read** the configuration.
7. Monitor objects and costs. Do not misjudge results immediately if the background process has not run yet.

To avoid accidental data loss, test only on a **lab bucket** containing non-critical data or a test prefix approved by its owner.

### 9.3. Read-Only CLI Inspection

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="yaml(name,location,autoclass,lifecycle,softDeletePolicy,retentionPolicy,versioning)"

# List objects to verify prefix (read-only)
gcloud storage ls gs://BUCKET_NAME/temp/

# Inspect metadata of a single object without downloading data
gcloud storage objects describe gs://BUCKET_NAME/temp/sample.txt \
  --format="yaml(name,size,storageClass,timeCreated,updated)"
~~~

Although reading metadata does not trigger Autoclass promotions, commands that access **object data** (like download or `cat`) can cause an Autoclass object to transition back to Standard. When observing cooling behavior in experiments, avoid accidentally reading object content.

### 9.4. Applying Lifecycle JSON via CLI

After **preparing a JSON file outside the lesson** (e.g., `lifecycle.json` containing the complete rule set), run:

~~~bash
# MUTATING bucket; do not run in production without review
gcloud storage buckets update gs://BUCKET_NAME \
  --lifecycle-file=lifecycle.json
~~~

**Crucial:** This command **replaces the entire existing lifecycle configuration**. If the bucket already has other rules, your JSON file must include every existing rule you want to preserve. Never supply a file containing only one new rule if your intent is to "append" a rule.

If you need to clear all lifecycle rules (mutating; not a default rollback):

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --clear-lifecycle
~~~

Clearing delete rules **does not restore** already-deleted objects and **does not guarantee immediate halt** of actions already scheduled during the propagation window.

### 9.5. Sample JSON for an Enterprise Scenario

Bucket `gs://order-artifacts-lab` without Autoclass needs:

- `reports/` moved to Coldline when at least 90 days old and sufficiently large.
- `temp/` deleted after 30 days.
- Incomplete XML multipart uploads aborted after 7 days.

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesPrefix": ["reports/"],
        "sizeAboveBytes": 131072
      }
    },
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"]
      }
    },
    {
      "action": { "type": "AbortIncompleteMultipartUpload" },
      "condition": {
        "age": 7
      }
    }
  ]
}
~~~

**Do not apply this JSON to an Autoclass bucket.** Remove the `SetStorageClass` rule and keep Delete/Abort if combining Autoclass + lifecycle.

## 10. Interaction with Soft Delete, Versioning, Retention, and Object Holds

Data protection features determine **when Delete actually causes bytes to disappear**.

### 10.1. Soft Delete

Soft delete can retain an object after deletion for a **soft delete retention duration** (often defaulting to **7 days** on new buckets, though you must inspect the actual configuration). During this window, objects can be restored with sufficient permissions before expiration.

- Lifecycle `Delete` can place objects into the **soft-deleted** state.
- Lifecycle rules **do not apply** to soft-deleted objects: they neither transition classes nor get permanently purged by rules.
- Autoclass also **does not transition** soft-deleted objects; **Autoclass management fees do not apply to soft-deleted objects**.
- Restoring a soft-deleted object in an Autoclass bucket restores it in **Standard**.

This explains why billing still shows storage charges after an object is deleted until soft delete retention expires. **Do not disable soft delete just to make storage numbers drop immediately** if the data requires recoverability.

### 10.2. Object Versioning

When Object Versioning is enabled:

- Overwriting or deleting a live generation can turn it into a **noncurrent generation**.
- If your rule only specifies `isLive:true`, old versions can **accumulate indefinitely** and incur storage charges.
- You can use `isLive:false` and `daysSinceNoncurrentTime` to manage the age of noncurrent generations.
- If soft delete is also enabled, deleting a noncurrent version may move that version to soft-deleted state before permanent removal.

A policy like "keep only the 3 newest versions" should use conditions like `numNewerVersions` and `isLive:false` by design, while verifying retention requirements and per-generation rollback needs.

### 10.3. Retention Policy / Object Holds

**Bucket retention policies**, **Object Retention Lock**, and **object holds** are not lifecycle rules. They protect data from premature deletion or while a hold remains active.

- If an object has an active hold or has not satisfied its retention period, lifecycle `Delete` **cannot delete it** even when age thresholds are met.
- Once the hold/retention expires, if the object still matches the Delete rule, the system can delete it afterward.
- Autoclass managing storage class **does not alter retention constraints**.
- Once a bucket has **Bucket Lock**, the retention policy may not be shortened or removed; do not apply locks in lab exercises.
- For compliance mandates such as 7-year retention, lifecycle Delete after 7 years only executes when retention and holds allow it; verify with legal and governance before deploying.

### 10.4. Difference Between Retention and Lifecycle Delete

| Mechanism | Purpose | When an Object Qualifies |
| --- | --- | --- |
| Retention | **Prevents** premature deletion | After expiration, it **can be deleted** by a job or rule |
| Lifecycle Delete | **Requests** deletion when conditions match | Deletes **asynchronously**, unless retention/holds block it |
| Soft delete | **Allows recovery after deletion** within configured window | Once the window expires, the object is permanently deleted |
| Versioning | **Keeps old copies** on overwrite/delete of live version | Noncurrent versions persist until deleted per policy |

**Setting a 365-day retention policy does not mean the object will automatically be deleted on day 366.** Automatic TTL requires a lifecycle Delete rule or a dedicated cleanup workflow.

## 11. Workflow for Choosing Autoclass vs. Lifecycle for a Workload

Instead of asking "Does Autoclass save money?", describe the **data behavior and contract** first:

1. **What is the data?** User images, logs, backups, reports, ML datasets, artifacts, compliance records?
2. **Object size:** How many objects are under 128 KiB? What is the total object count and byte distribution by size bucket?
3. **Read frequency:** Predictable or highly variable? Are there periodic scan jobs, lifecycle batches, or compliance reads?
4. **Retention duration:** How long is legally required? When is deletion allowed? Are soft delete/versioning/holds active?
5. **Retrieval needs:** Are old objects read often? Are there strict RTO/RPO targets or high request/egress costs?
6. **Operation counts:** PUT, GET, LIST, COPY/REWRITE, and transition counts if using lifecycle?
7. **Region/security requirements:** Location, encryption, IAM, access policies, and auditing.
8. **Quantitative cost:** Storage class pricing by location, management/enablement fees, Class A ops, retrieval, early deletion, egress, and soft delete.

~~~mermaid
flowchart TD
  START["Data in Cloud Storage"] --> RET{"Age- or version-based retention/deletion needed?"}
  RET -- "Yes" --> DEL["Design retention + lifecycle Delete"]
  RET -- "No" --> ACCESS{"Is read frequency hard to predict?"}
  DEL --> ACCESS
  ACCESS -- "Yes" --> SIZE{"Are most bytes in objects >= 128 KiB?"}
  SIZE -- "Yes" --> AUT["Evaluate Autoclass + Delete if needed"]
  SIZE -- "No" --> MAN["Evaluate Standard / targeted rules"]
  ACCESS -- "No" --> CLASS{"Are class transition times clearly known?"}
  CLASS -- "Yes" --> LC["Evaluate lifecycle SetStorageClass\non a NON-Autoclass bucket"]
  CLASS -- "No" --> AUT
  AUT --> COST["Calculate TCO, check enablement and GET impact"]
  MAN --> COST
  LC --> COST
  COST --> VERIFY["Lab + permission review + verify in Billing"]
~~~

### 11.1. Three Quick Decision Questions

**A. Should data expire and be deleted automatically?**

If yes, you need **Lifecycle Delete**, even if Autoclass is enabled. Autoclass never deletes data just because nobody read it for years.

**B. Does the operations team know in advance which objects are "hot" and which are "cold"?**

If already known by prefix or business workflow (e.g., `reports/final/` must stay 5 years and is rarely read), an age-based class and deletion policy can be simpler and easier to forecast. If images/product data may unexpectedly get read again, Autoclass is a strong candidate.

**C. Does the bucket already hold a large volume of cold-class data?**

If yes, the **one-time enablement charge** when switching to Autoclass may outweigh short-term gains. Test on a new bucket or a separate dataset rather than enabling Autoclass wholesale on legacy buckets without calculations.

## 12. Four Real-World Application Scenarios

### 12.1. Images and User Documents with Unpredictable Access Patterns

**Context:** A Java API / Cloud Run service stores electronic invoices, product images, and user documents. Objects are heavily read right after creation, yet old documents are occasionally re-downloaded.

**Approach:**

- A new bucket with **Autoclass** if most bytes live in objects 128 KiB or larger.
- Terminal `NEARLINE` if you do not want Coldline/Archive transitions; consider `ARCHIVE` if large volumes go unread for years.
- Use Lifecycle `Delete` for **temporary uploads**, never deleting images/invoices still within retention.
- If using Cloud CDN, compare hit ratio against actual GETs reaching the Cloud Storage origin.
- Measure request costs and Autoclass management fees; consider Cloud Billing budgets.

**Risk:** A periodic job reading every object's content for indexing, DLP, or checksum verification can keep all data continuously hot. Check actual read schedules rather than just user-facing traffic.

### 12.2. Log Files for Incident Investigation

**Context:** Logs exported as `logs/app/2026/11/...`, retained for 90 days; mostly read only during incidents.

**Candidate:** Standard or Nearline bucket with **Lifecycle Delete at `age:90`**. If byte volume is large and access is unpredictable, Autoclass can make sense, provided you check object sizes and scan pipelines.

**Points to verify:**

- Do logs contain personally identifiable information? Are they audit records needing longer retention?
- Are new objects tiny (a few KiB) or compacted/partitioned into larger files?
- Which system exports the logs, and is the bucket **managed by another Google Cloud service**?
- Is Delete aligned with retention/soft delete/versioning and forensics needs?

Never arbitrarily configure lifecycle rules on buckets managed by Artifact Registry or other services: deleting system-owned objects can break artifacts or deployments.

### 12.3. Backups and Long-Term Data with a Clear Schedule

**Context:** Immutable database backups taken daily, required for 365 days, restored only during outages.

**Candidate:** Appropriate storage class and **Lifecycle Management** matching retention/deletion policy; Autoclass is usually unnecessary since the access pattern is predictable.

**Decisions needed:**

1. Are backups sufficiently isolated from the data source, and is a secondary copy/another region needed?
2. Are Object Versioning, soft delete, or retention locks enabled to defend against malicious deletion?
3. If placed in Archive from day one, are retrieval/early deletion costs acceptable if deleted early?
4. Should deletion rules use **creation date** or the backup cycle's **Custom-Time**?
5. Are restores tested periodically? Does restore testing trigger GETs that alter Autoclass behavior?

**Conclusion:** Autoclass optimizes class costs, **not backup/DR**. Data in Archive can still be deleted if IAM or Lifecycle is misconfigured without retention protection.

### 12.4. Temporary Data for BigQuery/ML Pipelines

**Context:** Pipelines write CSV/Parquet files under `staging/` and `temp/`, useful for under 14 days; failed jobs occasionally leave incomplete multipart uploads behind.

**Candidate:** Dedicated bucket with **Lifecycle Delete `age=14` + `matchesPrefix`** and **`AbortIncompleteMultipartUpload age=7`**; cold-class optimization is unnecessary if all data is deleted quickly.

**Risk:** Slow jobs or retries after 15 days may fail to find files. Base TTL on workflow lifetimes and SLAs rather than picking the shortest window solely to cut storage cost.

## 13. Organizing Data and Versions So Lifecycle Rules Do Not Cause Data Loss

### 13.1. Separate Buckets or Separate Prefixes?

| Option | Advantages | Limitations |
| --- | --- | --- |
| **One bucket, multiple prefixes** | Fewer buckets, simple rollout, prefix-scoped rules | Autoclass applies bucket-wide; IAM/retention harder to separate; mistakes affect multiple groups |
| **Multiple buckets by data class** | Independent Autoclass/lifecycle/retention; clear ownership | Requires managing IAM, DNS/URIs, quotas, and billing cleanly |
| **Managed folders / hierarchical namespace** | Structured organization and access governance as supported | Does not replace reviewing lifecycle/class rules; check product limits |

**Design Rule:** If two datasets have **very different** retention policies and read frequencies, separating buckets avoids a single shared Autoclass policy or an overly broad Delete rule. If they only differ by prefix while sharing SLAs and retention, a shared bucket with prefix-filtered lifecycle rules can work well.

### 13.2. Naming Conventions That Support Safe Deletion

Object names should be easy to audit:

~~~text
temporary/session-<id>/<filename>
reports/daily/YYYY/MM/DD/<filename>
reports/monthly/YYYY/MM/<filename>
backups/service/2026-11-19T00-00-00Z/<filename>
legal-hold/case-<id>/<filename>
~~~

**Never use a `temp/` prefix to store both temporary scratch files and invoices requiring 7-year retention.** `matchesPrefix` is case-sensitive and inspects only the **object name**—it understands nothing about business semantics.

### 13.3. Newly Uploaded Data and Retry Logic

A pipeline might perform a resumable or multipart upload over several hours. Object age for `age` rules starts only once the **object upload completes** (for XML multipart uploads, age in Abort rules starts when the **upload begins**). TTL designs should not assume age starts at job launch if the object is not yet finalized.

If a workflow retries and overwrites an object with the same name:

- The **new generation's** creation timestamp differs from the old generation.
- Object Versioning may retain the old generation.
- Lifecycle Delete can act independently on each generation based on conditions.
- Applications must enforce idempotency and generation preconditions on writes/deletes to prevent unintended overwrites.

### 13.4. Data Residency and Encryption

Autoclass does not move a bucket's data location. It does not make exported data safer, nor does it replace:

- **IAM** on buckets/objects, service accounts, and managed folder policies.
- **Uniform bucket-level access** and **Public access prevention**.
- **VPC Service Controls** for supported products when using a perimeter.
- **CMEK/CSEK**, key rotation management, and decryption access controls.
- Retention, object holds, audit logs, and incident response.

A bucket sitting in cheap Archive storage with a misconfigured public-read policy is still a severe security incident.

## 14. Monitoring Autoclass and Lifecycle Effectiveness

### 14.1. Monitoring Metrics for Autoclass

Google Cloud Monitoring exposes metrics for class transitions:

| Metric Suffix | Interpretation |
| --- | --- |
| `autoclass/transition_operation_count` | Number of Autoclass storage class transitions, excluding transitions triggered by initial enablement |
| `autoclass/transitioned_bytes_count` | Total bytes transitioned by Autoclass, also excluding enablement transitions |

Metrics can be grouped by **source/destination storage class**. In the Cloud Storage Console, go to the bucket → **Configuration → See Performance** to observe byte distribution by class over time when available for that bucket.

**How to interpret:**

- Right after enabling Autoclass on an existing bucket, Standard volume may spike due to resets; transition metrics exclude enablement transitions.
- Steady transitions to Nearline/Coldline usually indicate unread objects. Frequent GETs promoting objects back to Standard may signal a scanning pipeline warming the data.
- Transitions are asynchronous, so metrics will not align to exact 30/90/365-day boundaries per object.

### 14.2. Reading Metadata Without Accidentally Warming Objects

These commands only read metadata or list objects:

~~~bash
# Bucket details
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="yaml(autoclass,lifecycle,location,softDeletePolicy,versioning)"

# Metadata of 1 object; does not download data
gcloud storage objects describe gs://BUCKET_NAME/reports/monthly/sample.csv \
  --format="yaml(name,storageClass,size,timeCreated,updated)"
~~~

**Do not run `gcloud storage cat` or `gcloud storage cp gs://... ./local` just to inspect an object's class** while observing cooling behavior, because reading content can trigger Autoclass to promote the object back to Standard.

### 14.3. Reconciling Billing and Application Performance

A FinOps dashboard can track:

- Total bytes in Standard/Nearline/Coldline/Archive by bucket and region.
- Object counts by size bucket: under 128 KiB, 128 KiB–1 MiB, 1–100 MiB, over 100 MiB.
- Autoclass management charges, enablement charges, operations, and class transitions.
- Retrieval/early deletion charges on **non-Autoclass** buckets or during migrations.
- Soft-deleted / noncurrent storage.
- Objects eligible for Delete that have not yet been processed.
- Cloud Storage request counts, network egress, API latency, and error rates.
- Cost spikes following an application release that increases GETs.

Use **Cloud Billing Reports**, **Budgets**, or **Cloud Billing export to BigQuery** to analyze charges by SKU, project, and billing period. When comparing before and after changes, hold region, byte volume, user traffic, and observation window constant for valid conclusions.

### 14.4. Defining Effectiveness Metrics

An Autoclass report should not simply say "moved 5 TB to Archive." It should answer:

1. What were total storage and management costs **before vs. after**?
2. Has the enablement charge been amortized across the evaluation period?
3. How many objects under 128 KiB are ineligible for class transitions?
4. How many objects were read again, and what Class A transitions occurred?
5. Did GET frequency, egress, or scanning jobs change?
6. Did application data retrieval change, and were there any 403/404 errors?
7. Are retention, soft delete, versioning, and data governance policies still intact?

## 15. Guided Lab: Comparing Two Buckets

**Goal:** Configure one bucket with **Autoclass + Lifecycle Delete** and one bucket with **Lifecycle SetStorageClass** without Autoclass, verify via metadata, and explain the trade-offs.

**Note:** The create/update/delete commands below **modify real resources and may incur charges**. Run only in an approved lab project. Observing real class transitions requires data to remain unread for **30/90/365 days**; you can complete the configuration and verification steps immediately without waiting for those durations.

### 15.1. Prepare Test Resources

Create two globally unique bucket names:

~~~text
gs://UNIQUE_AUTOC-LAB_BUCKET     (Autoclass)
gs://UNIQUE_MANUAL-LAB_BUCKET    (Lifecycle SetStorageClass)
~~~

These are placeholders; replace with valid names permitted by your organization, avoiding `_` if disallowed by naming rules. Place both buckets in the same location for a fair cost comparison.

Use the CLI to check your project:

~~~bash
gcloud config get-value project
gcloud storage buckets list --project=LAB_PROJECT_ID
~~~

Create the lab buckets if authorized (substitute real names):

~~~bash
gcloud storage buckets create gs://AUTOC_BUCKET \
  --project=LAB_PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access

gcloud storage buckets create gs://MANUAL_BUCKET \
  --project=LAB_PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access
~~~

**Do not use buckets holding live artifacts/images or real backups.** Check project data protection, IAM, and default soft delete settings; do not make objects public.

### 15.2. Enable Autoclass on Bucket A

~~~bash
# Mutates bucket: lab only
gcloud storage buckets update gs://AUTOC_BUCKET \
  --enable-autoclass \
  --autoclass-terminal-storage-class=NEARLINE

# Read back
gcloud storage buckets describe gs://AUTOC_BUCKET \
  --format="default(autoclass)"
~~~

Expected result: `autoclass.enabled: true` and terminal `NEARLINE`. If the bucket has a non-Standard default class, include `--default-storage-class=STANDARD` when enabling.

### 15.3. Configure a Delete Rule for Bucket A

Create a file **on your lab machine** (not inside the lesson directory) named `lifecycle-autoc.json`:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"]
      }
    }
  ]
}
~~~

Apply it:

~~~bash
# Update replaces all existing lifecycle rules
gcloud storage buckets update gs://AUTOC_BUCKET \
  --lifecycle-file=lifecycle-autoc.json
~~~

Verify:

~~~bash
gcloud storage buckets describe gs://AUTOC_BUCKET \
  --format="yaml(autoclass,lifecycle)"
~~~

This example is valid because it uses **Delete** with age and prefix, without `SetStorageClass` or `matchesStorageClass`.

### 15.4. Configure a SetStorageClass Rule for Bucket B

Create `lifecycle-manual.json`:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "NEARLINE"
      },
      "condition": {
        "age": 30,
        "matchesPrefix": ["reports/"]
      }
    },
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 180,
        "matchesPrefix": ["temp/"]
      }
    }
  ]
}
~~~

Apply **only to Bucket B without Autoclass**:

~~~bash
gcloud storage buckets update gs://MANUAL_BUCKET \
  --lifecycle-file=lifecycle-manual.json
~~~

Here, if Bucket B accidentally had Autoclass enabled, the command with `SetStorageClass` would be rejected due to compatibility rules; never blindly disable Autoclass on a shared bucket to "fix the error."

### 15.5. Upload and Inspect Object Status

Assuming your lab machine has a **non-sensitive** file named `sample.txt`:

~~~bash
gcloud storage cp ./sample.txt gs://AUTOC_BUCKET/temp/sample.txt
gcloud storage cp ./sample.txt gs://MANUAL_BUCKET/temp/sample.txt
gcloud storage ls gs://AUTOC_BUCKET/temp/
gcloud storage ls gs://MANUAL_BUCKET/temp/
~~~

Read metadata without downloading data:

~~~bash
gcloud storage objects describe gs://AUTOC_BUCKET/temp/sample.txt \
  --format="yaml(name,size,storageClass,timeCreated)"

gcloud storage objects describe gs://MANUAL_BUCKET/temp/sample.txt \
  --format="yaml(name,size,storageClass,timeCreated)"
~~~

**Expected right after upload:** Autoclass places the new object in Standard. The manual bucket uses the default class chosen at creation; lifecycle will not immediately transition or delete an object before it reaches the required age.

### 15.6. Comparison Table to Complete

| Question | Bucket A: Autoclass | Bucket B: Manual Lifecycle |
| --- | --- | --- |
| Who decides the class? | Google based on GET history | `SetStorageClass` rule based on age/prefix |
| Will a 32 KiB object move to Nearline via Autoclass? | No | Can be transitioned by a matching rule; check Class A fee |
| What happens when a Nearline object is read again? | Autoclass can promote it back to Standard | Remains Nearline unless rewritten/changed separately |
| Which Delete rule is active? | `temp/` from age 30 | `temp/` from age 180 |
| Can `matchesStorageClass` be used? | No | Yes, if rules are valid |
| Is there an Autoclass management fee? | Yes for eligible objects | No |
| Is there a Class A fee for `SetStorageClass`? | No, because no `SetStorageClass` rule exists | Yes, when the rule transitions objects |
| Are soft delete/retention active? | Depends on bucket configuration | Depends on bucket configuration |

**Never test "quick deletion" by setting `age:0` on a production bucket.** A new rule can immediately target older qualifying objects, and deletion/restoration offers no guaranteed zero-loss rollback.

### 15.7. Lab Cleanup

- Re-check object listings, lifecycle, retention, soft delete, and versioning.
- Delete **only the objects and buckets created specifically for this lab**, after confirming ownership.
- If objects remain soft-deleted, bucket deletion may be restricted; follow documented cleanup steps instead of forcing deletion.
- If a bucket has a retention lock, you cannot simply remove the lock to clean up.
- Never run recursive delete commands with wildcards targeting buckets outside the lab.
- Verify billing after cleanup; soft-delete storage or logs/monitoring may continue incurring minor charges during their retention window.

## 16. Troubleshooting and Frequently Asked Questions

| Symptom | Common Cause | Investigation / Remediation |
| --- | --- | --- |
| Cannot enable Autoclass | Lifecycle contains `SetStorageClass` or `matchesStorageClass` | Inspect current lifecycle and redesign compatible rules; never blindly delete data-protection rules |
| Enabled Autoclass, but objects still show old class | Enablement is propagating / metadata has not updated yet | Check `autoclass.enabled`, enablement time, and billing policy; do not judge from a single object |
| Autoclass is enabled, but new objects do not move to Nearline | Under 30 unread days, smaller than 128 KiB, or periodic GETs occur | Check object size, access pattern, terminal class, and eligibility window |
| Coldline/Archive never appears | Terminal class is `NEARLINE` or objects have not aged enough | Check terminal class; only `ARCHIVE` enables the 90/365-day path |
| Object unexpectedly promoted back to Standard | An app, job, or scanner issued a GET for content | Inspect request logs and data-access patterns, not just metadata |
| Costs spiked when enabling Autoclass on an existing bucket | One-time enablement charge / objects reset to Standard | Reconcile Billing SKUs, total bytes, and prior classes |
| Disabled Autoclass, yet reads still incur cold-class fees | Object classes did not revert to Standard | Check object `storageClass` and post-disable pricing model |
| Lifecycle `SetStorageClass` rejected | Bucket has Autoclass enabled | Use a non-Autoclass bucket or remove `SetStorageClass` |
| Delete with `matchesStorageClass` rejected | Autoclass prohibits this condition even for Delete | Use `age`, prefix, `isLive`, or `customTime` instead |
| Object reached age threshold but is not deleted | Lifecycle is asynchronous; active retention/hold; soft delete/versioning | Check rule, `timeCreated`, live/noncurrent state, holds/retention |
| Still billed for bytes after deletion | Soft-deleted or noncurrent versions are retained | Check soft delete duration, generations, and retention |
| New rule deleted older objects | Configuration replaced all rules, or old rule propagated up to 24h | Restore from soft delete/versioning if available; audit and tighten review process |
| `SetStorageClass` generated high operation fees | Millions of small objects matched at once | Calculate Class A fees, add size filter, or separate buckets |
| Cold-class GETs are expensive in manual bucket | Cold-class retrieval, operation, and egress fees | Estimate GET frequency; evaluate Standard or Autoclass |
| Incomplete multipart uploads consuming storage | Missing `AbortIncompleteMultipartUpload` or mismatched conditions | Use Abort action matching XML multipart API and valid age |
| Object access returns `403` | IAM, KMS, ACL/PAP, retention, or Org Policy depending on action | Check permissions directly; do not change storage class to "fix access" |
| Object compose fails in Autoclass | Source objects are not simultaneously in Standard | Follow Autoclass compose requirements and check source classes first |
| Cannot delete lab bucket | Remaining objects/versions/soft-deleted items, retention/hold, or other settings | Verify exact bucket state and follow supported cleanup procedures |

### 16.1. Safe Diagnostic Order to Avoid Data Loss

~~~text
Correct bucket, project, and owner?
  ↓
Is Autoclass enabled, and with which terminal class?
  ↓
What rules exist in the current lifecycle configuration?
  ↓
Which object, size, generation, creation time, live/noncurrent?
  ↓
Recent data GETs? Any scanners, batch jobs, or caching layers?
  ↓
Are soft delete, retention policy, or object holds active?
  ↓
Has enough time elapsed considering asynchronous propagation delay?
  ↓
Do charges stem from storage, operations, enablement, or egress?
  ↓
Propose change + backup/rollback + approval
~~~

**Avoid knee-jerk fixes without evidence:** Do not toggle Autoclass on and off repeatedly when costs rise; do not change Delete age from 10 to 100 days assuming existing data is instantly safe; do not manually force storage class changes on an Autoclass bucket.

## 17. Scenario Exercises and Guided Answers

### Exercise 1 — Re-Reading an Old Image

A 4 MiB image object is uploaded to an Autoclass bucket with terminal `ARCHIVE`. It is never read after upload. After **40 days**, which class should it be in theoretically? If it is GET-accessed on day 50 and then unread for another 100 days, what are the expected milestones?

**Hint:** After 40 days it is eligible for **Nearline** (executed asynchronously); a GET on day 50 promotes it to **Standard**. Starting a new cycle from that GET: after 30 unread days → Nearline; by 90 unread days → Coldline; at 100 unread days, it is theoretically eligible for Coldline, not yet Archive.

### Exercise 2 — One Million Small Objects

A bucket contains 1 million objects, each 16 KiB, rarely read. Should you expect Autoclass to move all of them to Nearline after 30 days?

**Hint:** No. Objects **smaller than 128 KiB** always stay in Standard under Autoclass. Revisit data layout and lifecycle/retention rather than relying on auto-tiering to cut costs.

### Exercise 3 — Two Interpretations of Age

A rule sets `Delete age=90` for `reports/`. An object is uploaded on day 1 and read again on day 89. Will it qualify for Delete on day 91?

**Hint:** Yes, because lifecycle `age` is measured **from creation time** and does not reset on GET. Autoclass may change storage class on GET, but it does not alter age-based Delete rules.

### Exercise 4 — Conflict When Enabling Autoclass

A bucket has a Delete rule: `age:365, matchesStorageClass:["ARCHIVE"]`. Can Autoclass be enabled right away? If the goal is simply deleting old files, how should you adjust it?

**Hint:** No, `matchesStorageClass` is incompatible. Remove the class condition and use `age` plus an appropriate prefix/data category after reviewing data retention policies.

### Exercise 5 — Soft Delete and Versioning

A bucket has both Object Versioning and soft delete enabled. The Delete rule only has `isLive:true` and `age:30`. Will costs drop to zero after 30 days?

**Hint:** No. Live objects can become noncurrent, and noncurrent generations are not deleted by that rule. When noncurrent versions are later deleted, soft delete can retain them further. Review retention and billing before setting cleanup rules for old versions.

### Exercise 6 — Age-Based Class Optimization

A non-Autoclass bucket transitions objects to Nearline at day 30, Coldline at day 90, Archive at day 365, and deletes objects at day 400. What must be factored into the cost evaluation?

**Hint:** Class A operations for each `SetStorageClass`, storage fees in each tier, network/request/retrieval costs, and potential early deletion charges when deleting an Archive object before it spends 365 days in that class. Do not confuse "age 400 from creation" with "365 days spent in Archive."

### Exercise 7 — "Does Enabling Autoclass Always Save Money?"

A bucket holds 20 TB of Archive data over a year old that is rarely read. Should you enable Autoclass because Archive is cheap?

**Hint:** Not necessarily. Enabling resets existing objects to Standard and triggers a one-time enablement charge. If access patterns are stable, keeping the current class may be better.

### Exercise 8 — Updating a Delete Rule

An operator changes Delete from `age:7` to `age:30` after noticing files are being deleted too soon. Can they guarantee all 8–29-day-old files are immediately safe?

**Hint:** No. The previous rule can continue taking effect for up to **24 hours** after the update. Data protection safeguards and review workflows are needed before deploying destructive rules.

### Exercise 9 — Distinguishing Rollback and Restore

You removed the `Delete` rule from a bucket and re-enabled Autoclass. Does that restore already-deleted objects?

**Hint:** No. Changing rules is not a restore. Recovery is only possible if valid soft-deleted copies, noncurrent generations, backups/replicas, or another recovery mechanism remain available.

## 18. Pre-Production Checklist

- [ ] Verify project, bucket owner, location, data classification, and data residency.
- [ ] Measure bytes and object counts by size bucket: check how many are under 128 KiB.
- [ ] Know real access patterns, scan jobs, CDN/Cloud Storage FUSE usage, and GET volume.
- [ ] Choose Autoclass or lifecycle based on workload requirements, not per-GiB price alone.
- [ ] If Autoclass: confirm terminal class (`NEARLINE`/`ARCHIVE`) and 30/90/365-day milestones.
- [ ] If enabling Autoclass on a populated bucket: estimate one-time enablement charge, management fee, and Standard reset.
- [ ] If using lifecycle: JSON includes **all rules to keep**; AND/OR logic, prefixes, and versioning reviewed.
- [ ] **No** `SetStorageClass` or `matchesStorageClass` present when Autoclass is enabled.
- [ ] Do not configure lifecycle directly on buckets managed by other services unless supported.
- [ ] Check minimum duration, Class A fees, and retrieval/early deletion when not using Autoclass.
- [ ] Verify soft delete duration, Object Versioning, retention, holds, and legal policies.
- [ ] Never store critical objects under a `temp/` prefix alongside deletable scratch data.
- [ ] Backup/restore tested; team understands lifecycle is asynchronous and old rules can apply for up to 24 hours.
- [ ] Least-privilege IAM, Uniform bucket-level access, Public access prevention, and auditing configured.
- [ ] Dashboards monitor costs, storage classes, transitions, and deleted/soft-deleted data.
- [ ] Approval, lab testing, rollback plan, and accountable owner established.
- [ ] Evaluated network and operation costs, not only at-rest storage.
- [ ] Recovery runbook exists in case Delete, retention, or versioning was misconfigured.

## 19. Official Google Cloud Documentation

Pricing details, supported capabilities, and CLI flags may change over time. When implementing in live environments, consult the official pages:

- [Autoclass overview](https://docs.cloud.google.com/storage/docs/autoclass) — principles, terminal classes, 128 KiB threshold, access behavior, restrictions, monitoring.
- [Use Autoclass](https://docs.cloud.google.com/storage/docs/using-autoclass) — enabling, disabling, changing terminal class via Console and `gcloud storage`.
- [Object Lifecycle Management](https://docs.cloud.google.com/storage/docs/lifecycle) — actions, conditions, rule precedence, versions, and deletion behavior.
- [Manage object lifecycles](https://docs.cloud.google.com/storage/docs/managing-lifecycles) — setting/uploading JSON, CLI, propagation, and permission requirements.
- [Object Lifecycle Management configuration samples](https://docs.cloud.google.com/storage/docs/lifecycle-configurations) — practical rules for common scenarios.
- [Cloud Storage classes](https://docs.cloud.google.com/storage/docs/storage-classes) — Standard/Nearline/Coldline/Archive and minimum storage duration.
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — storage, Class A/B operations, retrieval, Autoclass management/enablement, data transfer.
- [Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete) — retention window, restore, and lifecycle interaction.
- [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning) — live/noncurrent generations and recovery.
- [Bucket Lock and retention policies](https://docs.cloud.google.com/storage/docs/bucket-lock) — data retention and non-deletability constraints.
- [Object holds](https://docs.cloud.google.com/storage/docs/object-holds) — temporary holds and event-based holds.
- [gcloud storage buckets update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update) — Autoclass flags, lifecycle files, and bucket features.
- [Cloud Storage monitoring](https://docs.cloud.google.com/storage/docs/monitoring) — metrics and observability.
- [Cloud Billing export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — analyzing actual costs by project/SKU.

**Conclusion:** **Autoclass** automates storage class selection based on data read history; **Object Lifecycle Management** executes age, version, and prefix rules that you define. You can combine **Autoclass + Lifecycle Delete** in the same bucket, but you cannot combine Autoclass with `SetStorageClass` or `matchesStorageClass`. The best decision also accounts for object sizes, transition charges, retention durations, soft delete, versioning, and actual billing metrics rather than looking only at storage price per GB.

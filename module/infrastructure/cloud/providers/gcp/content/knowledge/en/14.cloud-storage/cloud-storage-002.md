# Choosing Bucket Location and Storage Class in Google Cloud Storage

A development team runs an e-commerce platform on **Google Cloud**. A **Cloud Run** application receives product images, a **GKE** pipeline transforms images, **Compute Engine** processes reports, and **Cloud SQL** stores metadata. New images are read thousands of times per day, old reports are only reviewed quarterly, and backups must be retained long-term for regulatory compliance. If the team chooses the same **bucket location** and **storage class** for everything, the organization may pay unnecessary fees or fail to meet data residency and disaster recovery requirements.

**Cloud Storage** is an **object storage** service: data is stored as objects in buckets and accessed via APIs, SDKs, or CLI tools. When creating a bucket, two key decisions are:

1. **Bucket location:** which **region, dual-region, or multi-region** stores the data—affecting geographic scope, redundancy model, compliance with data requirements, network paths, and cost.
2. **Storage class:** choosing **Standard, Nearline, Coldline, Archive**, or an automated storage class management strategy where appropriate—affecting storage price, retrieval fees, early deletion/transition charges, and total lifecycle cost.

This lesson belongs to the **Cloud Storage** chapter of the **CLOUD_PROVIDERS_GCP** module. The broader goal of the module is to organize projects, manage IAM/VPC, choose among Compute Engine, GKE, Cloud Run, storage and database services, deploy securely, automate releases, and monitor reliability and cost. This lesson focuses on making **explainable and verifiable decisions** when placing data into buckets.

## 1. Learning Outcomes

After this lesson, learners will be able to:

1. Clearly distinguish **bucket**, **object**, **bucket location**, **default storage class**, and **per-object storage class**.
2. Compare **regional**, **dual-region**, and **multi-region** locations based on data requirements, fault tolerance, and cost.
3. Choose among **Standard, Nearline, Coldline, and Archive** based on access frequency, retention duration, and actual operation patterns.
4. Understand the impact of **minimum storage duration**, read/retrieval fees, and changing storage classes.
5. Distinguish **Autoclass** from custom **Object Lifecycle Management** rules.
6. Use `gcloud storage` to create and inspect buckets, manage the default storage class, and configure lifecycle rules safely.
7. Design storage for applications running on Cloud Run/GKE/Compute Engine while considering IAM, security, recovery, and cost optimization.

## 2. Three Foundational Concepts: Bucket, Location, and Class

### 2.1. Bucket and Object

A bucket is a logical container holding objects. An object has data, a name, and metadata. Example:

~~~text
Bucket: gs://retail-media-prod-example
Location: asia-southeast1
Default storage class: STANDARD

Objects:
  products/2026/11/item-1001.jpg
  products/2026/11/item-1002.jpg
  reports/monthly/2026-10.csv
~~~

Bucket names must be **unique within the applicable Cloud Storage namespace**, follow naming rules, and contain no sensitive information. The name in the example is illustrative only; do not assume you can create this exact name in your project.

**Location is a bucket property.** Each bucket has one storage location chosen from supported location types. **Storage class can be a per-object property**; the bucket's default storage class only determines the default class applied to new objects when no explicit class is specified.

### 2.2. Location and Storage Class Answer Different Questions

| Decision | Question to Answer | Example |
| --- | --- | --- |
| **Bucket location** | In what geographic scope and replication model does the data reside? | Region `asia-southeast1`, a supported dual-region, or multi-region `ASIA`. |
| **Storage class** | Which pricing tier fits the read frequency and retention duration? | Hot-selling images use `STANDARD`; long-retained reports may use `COLDLINE`. |
| **IAM/policy** | Who can read, write, delete, or publish objects? | The app's service account only reads/writes required objects. |
| **Lifecycle/retention** | When should classes change, objects be deleted, or data be locked for retention? | Transition classes after 90 days; retain data per legal obligations. |

A bucket placed in a dual-region containing an `ARCHIVE` object is still dual-region in location. A bucket in a single region using `STANDARD` does not automatically gain cross-region redundancy. **Location does not automatically change storage class, and vice versa.**

### 2.3. Data Path Diagram

~~~mermaid
flowchart LR
    U["Users / Applications"] --> API["Cloud Storage JSON/XML APIs"]
    API --> B["Bucket: chosen location"]
    B --> O1["Object A: STANDARD"]
    B --> O2["Object B: NEARLINE"]
    B --> O3["Object C: ARCHIVE"]
    I["IAM + security policies"] -. "Access control" .-> API
    L["Lifecycle / Autoclass (when configured)"] -. "Manages storage class" .-> B
~~~

The diagram illustrates logical layers. Cloud Storage **is not a folder residing on a VM disk**; `gs://...` is an object URI. VMs, GKE, and Cloud Run call the service over appropriate endpoints and networking mechanisms. Placing a bucket in the same region as an application does not automatically give the bucket a private VPC IP.

## 3. Choosing a Bucket Location

### 3.1. Regional Location

A **regional bucket** stores data within one specific region, such as `asia-southeast1`. Cloud Storage manages durability and availability within that region according to product specifications; you should not think of data as sitting on a single server or single zone.

**When to consider regional:**

- Cloud Run, GKE, or VM workloads operate primarily in a single region.
- Regulations require data to stay within a **specific region** and not replicate elsewhere.
- The organization wants tight control over data placement and wants to avoid a broader geographic footprint than needed.
- The system accepts a separate DR design for scenarios where an entire region is unavailable.

**Limitation to remember:** Regional storage does not mean a copy exists in another region. If the risk of losing access during a full-region outage is unacceptable, evaluate dual-region/multi-region or an appropriate replication/backup architecture.

### 3.2. Dual-Region Location

A **dual-region bucket** stores data redundantly across **two specific regions** supported by Google Cloud. Depending on the dual-region type, you can pick a **predefined pair** or configure two regions within the constraints of a **configurable dual-region**. Not every pair of regions is permitted.

~~~mermaid
flowchart TB
    APP["Applications and Google Cloud APIs"] --> BUCKET["Dual-region bucket"]
    BUCKET --> R1["Replica in region A"]
    BUCKET --> R2["Replica in region B"]
    APP -. "Availability must be verified" .-> BUCKET
~~~

Dual-region is suitable when:

- You require **cross-region durability/availability across two regions** within an acceptable geographic boundary.
- Services processing data in two regions need a shared storage bucket fitting the architecture.
- Operations teams want Cloud Storage-managed replication instead of manually copying individual objects.

**Do not confuse replication with backup.** If an application has permission to delete objects or write corrupted data, location-level replicas will still reflect those unwanted changes. Recovery from accidental deletion, ransomware, or application bugs requires **Object Versioning, soft delete, retention, or independent backup/replication** as appropriate.

### 3.3. Multi-Region Location

A **multi-region bucket** places data within a **broad geographic area** defined by Google Cloud—such as `US`, `EU`, or `ASIA`—with data stored redundantly across multiple regions in that area under the service's model.

A common goal is supporting applications and users across many areas within a broad geography while relying on Cloud Storage availability characteristics. However:

- You **cannot manually select every exact physical region** inside a multi-region.
- `ASIA` does not mean data is stored in every Asian region.
- Multi-region alone does not solve all **low-latency end-user read** requirements: for high-traffic static content, you still need to evaluate **Cloud CDN** and caching policies.
- It is not automatically cheaper than regional; storage, replication, transfer, and compute interaction prices may differ.

### 3.4. Comparison Table of the Three Location Types

| Criterion | Regional | Dual-Region | Multi-Region |
| --- | --- | --- | --- |
| Scope | One specific region. | Two supported regions. | Group of regions within a broad geographic area. |
| Placement control | Exact single region. | Two specific regions where supported. | Select geographic area, not every member region. |
| Suitability for single-region workloads | Usually the easiest choice to justify. | May fit if two-region redundancy is needed. | Must justify benefit against cost. |
| Data must stay in a single region | Best fit for strict geographic constraints. | Unsuitable if the second region is disallowed. | Usually unsuitable if strictly limited to one region. |
| Expectation for full-region outage resilience | Requires a separate DR plan. | Replicated across two regions by the service. | Multi-region redundancy by the service. |
| Cost factors | Regional pricing and related traffic. | Dual-region location, replication, and traffic pricing. | Multi-region, access, and traffic pricing. |

**There is no single best choice for all workloads.** An application mainly running in one region should usually evaluate **regional** first; only expand to **dual-region** or **multi-region** when multi-region data requirements exist, after evaluating legal criteria, RPO/RTO, and cost.

## 4. How Location Affects Networking, Latency, and Compliance

### 4.1. Placing Data Close to the Workload That Accesses It Most

Suppose a Cloud Run app, a GKE cluster, and VMs all run in `asia-southeast1`, frequently processing images in Cloud Storage. Choosing a regional bucket in the same region is a **reasonable starting option** to simplify design:

~~~text
Cloud Run / GKE / VM: asia-southeast1
Cloud Storage bucket: asia-southeast1
Cloud SQL:            appropriate region per data architecture
~~~

Benefits should be **verified**, not guessed:

- Latency per operation type (`GET`, `PUT`, object listing, chunk processing).
- Data volume transferred across zones/regions and how Google Cloud bills it in the actual topology.
- Whether the network path from Cloud Run/GKE/VM to Google APIs is securely configured.
- Cost when compute in one region reads objects from another region.

**Same region does not mean all data transfer is free**: pricing depends on source/destination services, network path, request type, and pricing terms. Always consult the pricing pages for Cloud Storage, Compute Engine, GKE, or Cloud Run.

### 4.2. Delivering Data to Global Users

Suppose users across many countries view product images. Choosing a multi-region bucket is not a complete substitute for **edge caching**. A viable pattern:

~~~mermaid
flowchart LR
    CLIENT["Internet clients"] --> CDN["Cloud CDN / edge cache"]
    CDN --> LB["Load balancer + backend bucket or appropriate backend"]
    LB --> GCS["Cloud Storage bucket"]
    APP["Cloud Run / GKE generating new images"] --> GCS
~~~

Cloud CDN reduces origin fetches on cache hits; latency depends on cache policy, geography, and user behavior. Public images may fit caching well; invoices or private user data generally require strict control over headers, cache keys, and authorization. Do not use a CDN to justify leaving a bucket public without proper access control.

### 4.3. Data Residency Requirements

If personal data may only be stored in one country or one region, verify:

1. Whether the **Cloud Storage-supported location** satisfies legal/internal storage mandates.
2. For dual-/multi-regions, whether **every region used to store data** is permitted.
3. Whether **logging, KMS keys, backups, object versions, temporary files**, and supporting systems meet the corresponding geographic rules.
4. Whether organization controls, such as an **Organization Policy with the resource locations constraint**, prevent creating resources in disallowed locations.

**A bucket location is not a legal certification by itself.** Coordinate with security and legal teams to clarify data classifications, contractual obligations, and retention duties.

### 4.4. VPC Access Does Not Mean "Internal" Bucket Access

A Compute Engine VM without an external IP can call the Cloud Storage API if **Private Google Access** (or another supported Google API connectivity option), DNS, routes, egress policies, and IAM are properly configured. A regional bucket does not automatically receive an IP inside your VPC subnet; location governs where data is stored, not the network path to the API.

Similarly, Cloud Run and GKE have their own egress and identity models. Do not assign an external IP to a VM or grant the Owner role just because a `gcloud storage` command failed; distinguish among DNS, TCP/TLS, token, and IAM failures.

## 5. Choosing a Storage Class: Standard, Nearline, Coldline, Archive

### 5.1. Access Frequency Is the Primary Criterion

Cloud Storage provides storage classes with distinct intended uses and pricing models:

| Storage Class | Typical Usage Pattern | Minimum Storage Duration to Avoid Early Deletion/Transition Fees* | Examples |
| --- | --- | --- | --- |
| **Standard** | Frequently accessed data, serving applications and active content. | No Nearline/Coldline/Archive-style minimum. | Frequently loaded product images, newly uploaded files. |
| **Nearline** | Relatively infrequently read data, roughly once a month or less. | **30 days**. | Rarely viewed reports, short-term backups. |
| **Coldline** | Rarely read data, roughly once a quarter or less. | **90 days**. | Periodic backups, archived data for occasional investigations. |
| **Archive** | Very rarely accessed data, targeted for long-term retention. | **365 days**. | Long-term records, data retained for compliance obligations. |

\* These figures are common **minimum storage durations** for the respective classes. Deleting, replacing, or changing the class early can incur an **early deletion charge** for the remaining days under product rules; enabling Versioning, soft delete, or retention can make lifecycle and cost behavior more complex.

These classes **do not mean "Archive takes hours to retrieve a file"** as with some offline tape-style storage services. Cloud Storage provides low-latency online access per product characteristics, though **retrieval** and **operations** fees for colder classes can be significant.

### 5.2. Lower Storage Price Does Not Guarantee Lower Total Cost

When choosing a class, evaluate all of these together:

- **Storage cost:** capacity × duration × price by class/location.
- **Retrieval charges:** volume of data read from classes that charge for retrieval.
- **Operations charges:** API request volume and operation types (`GET`, `LIST`, writes, metadata management, etc.) per pricing.
- **Early deletion charges:** if objects are deleted, replaced, or transitioned before the minimum duration.
- **Data transfer / network charges:** traffic sent to clients, compute services, or other regions.
- **Data protection costs:** object versions, soft delete, replication, audit/logging, management, and governance.

**Key mindset:** choose a class based on **total cost over a data lifecycle**, not just the lowest storage price per GiB/month.

### 5.3. A Clear Example

Two files of identical size:

~~~text
Object A: products/new-arrival.jpg
  - Read thousands of times per day.
  - May be replaced with a new image after a few days.

Object B: audit/2026/quarter-01.tar
  - Almost never read again.
  - Must be retained long-term under an approved policy.
~~~

For **Object A**, Standard is usually better because it avoids frequent retrieval fees and has no cold-class minimum duration. For **Object B**, Coldline or Archive can bring savings if the retention period is long enough and read frequency is genuinely low. However, if the audit file is inspected weekly or frequently rewritten, Archive can generate unsuitable costs.

### 5.4. Location and Storage Class Form a Decision Matrix

| Workload | Location to Evaluate | Class to Evaluate | Primary Rationale |
| --- | --- | --- | --- |
| Active product images, Cloud Run/GKE mainly in Singapore. | Regional `asia-southeast1`. | Standard. | Frequent access; compute primarily in one region. |
| Critical application data served across two supported regions. | Supported dual-region. | Standard or class matching actual frequency. | Replication decision is separate from class decision. |
| Reports retained six months, very rarely read. | Regional matching org requirements. | Coldline, after cost calculation. | Retention period likely covers the minimum duration. |
| Multi-year archives, restored only when needed. | Region/dual-/multi-region per DR and legal constraints. | Archive. | Rare access and long lifecycle. |
| Globally accessed user content with heavy read traffic. | Region/dual-/multi-region per origin design. | Standard + evaluate CDN. | Must assess caching, data, and distribution cost. |

Never assume dual-/multi-region always pairs with Standard or that Archive always pairs with regional. These are **two independent configuration dimensions** with service constraints you must check.

## 6. Default Storage Class vs. Object Storage Class

### 6.1. Default Only Applies When Creating New Objects

A bucket has a **default storage class** attribute. If a client uploads an object without specifying another class, the new object inherits the bucket's default class per API behavior. However, **existing objects retain their current storage class**; changing the default class does not automatically move or convert existing objects.

Example:

~~~text
Day 01:
  Bucket default = STANDARD
  Upload a.jpg -> STANDARD
  Upload b.jpg -> STANDARD

Day 15:
  Bucket default changed to NEARLINE
  a.jpg -> still STANDARD
  b.jpg -> still STANDARD
  Upload c.jpg -> NEARLINE (if no explicit class specified)
~~~

To transition existing objects to another class, you must use **Object Lifecycle Management**, **Autoclass**, or an API/tool-supported class rewrite operation. Check implications for minimum storage duration, retrieval charges, and versioning/retention state.

### 6.2. Can Multiple Classes Coexist in One Bucket?

Yes, a standard bucket can contain objects in different storage classes. That is why you must inspect **object-level class** during cost analysis rather than just reading the bucket's default class.

~~~text
gs://retail-data-example/
  incoming/new-file.csv       [STANDARD]
  reports/2026-06.csv         [NEARLINE]
  backups/2025-12.tar         [COLDLINE]
  compliance/2020.tar         [ARCHIVE]
~~~

Organizing by prefix (`incoming/`, `reports/`, `backups/`) helps structure data and lifecycle rules, but in a flat-namespace object storage model, prefix names do not automatically create separate permissions, lifecycles, or geographic locations. Advanced Cloud Storage namespace features, if used, must be evaluated separately.

## 7. Autoclass and Object Lifecycle Management

### 7.1. What Is Autoclass?

**Autoclass** is a bucket-level feature that lets Cloud Storage automatically manage object storage classes based on access patterns and supported policies. It fits well when an organization **cannot accurately predict per-object access frequency** or wants to reduce the operational overhead of maintaining many class rules.

Concept:

~~~mermaid
flowchart LR
    NEW["New / frequently accessed object"] --> HOT["Class suited for hot access"]
    HOT --> LESS["Less accessed after observation period"]
    LESS --> COLD["Appropriate colder class"]
    COLD --> REACCESS["Object is accessed again"]
    REACCESS --> MANAGE["Autoclass re-evaluates class per service behavior"]
~~~

This diagram illustrates the concept only, **not the exact algorithm or transition timings of Autoclass**. Consult current documentation to understand target classes, management fees, transition criteria, exceptions, feature-combination restrictions, and behavior when objects are read again.

**Do not assume Autoclass is always cheaper than every lifecycle rule.** A dataset with predictable age and access patterns can often be optimized well with custom lifecycle rules. Conversely, if individual objects have unpredictable behavior, Autoclass can reduce mistakes from manual class selection.

### 7.2. What Are Lifecycle Rules?

**Object Lifecycle Management** lets you declare rules acting on objects based on conditions such as **object age**, prefix, current storage class, and other supported criteria. Two common actions:

- **`SetStorageClass`**: transitions an object to a supported class when conditions are met.
- **`Delete`**: deletes objects per rules, subject to retention policies, object holds, versioning, soft delete, and other protection mechanisms.

Lifecycle example:

~~~mermaid
flowchart LR
    D0["Creation day: STANDARD"] --> D30["From day 30: NEARLINE"]
    D30 --> D90["From day 90: COLDLINE"]
    D90 --> D365["From day 365: ARCHIVE"]
    D365 --> END["Retain or delete per separate policy"]
~~~

These milestones are measured by **object age since creation**, not by default "30 days after the previous class transition." Setting `age: 90` means the object **has reached 90 days of age**; therefore, check the current storage class condition to avoid unintended transitions.

### 7.3. Sample Lifecycle JSON File

In a lab, a learner can **create a file** named `lifecycle.json` with the following contents:

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
        "matchesStorageClass": ["STANDARD"]
      }
    },
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesStorageClass": ["NEARLINE"]
      }
    },
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "ARCHIVE"
      },
      "condition": {
        "age": 365,
        "matchesStorageClass": ["COLDLINE"]
      }
    }
  ]
}
~~~

This is an **illustrative policy**, not a default configuration to apply to every bucket. It assumes objects live long enough and the classes are supported. You must account for minimum storage duration, object versions, lifecycle conditions, fees, and interactions when multiple rules apply simultaneously.

### 7.4. Be Careful with Delete Rules

A `Delete` rule can wipe out unintended data if its conditions are too broad or if lifecycle rules are enabled on a bucket containing mixed object types. Prepare:

1. A list of prefixes, objects, and versions in the intended scope.
2. Retention policies, object holds, soft delete, and versioning configurations.
3. Age thresholds and classes verified against **actual object values**.
4. A recovery plan and testing in a test bucket with non-sensitive data.
5. Monitoring after rule updates, because lifecycle runs **asynchronously** and does not guarantee second-accurate changes the instant an object qualifies.

For data with compliance retention obligations, **lifecycle Delete does not replace a retention policy**. Once a retention policy is **locked**, shortening the duration or removing it may be strictly restricted or irreversible under product rules; obtain security/legal approval before configuring.

### 7.5. Autoclass vs. Self-Managed Lifecycle

| Criterion | Autoclass | Manual Lifecycle Rules |
| --- | --- | --- |
| Read predictability | Good when behavior is irregular/unpredictable. | Good when age, prefix, and access patterns are well defined. |
| Operational complexity | Cloud Storage manages class transitions within supported scope. | Operations team validates rule logic and cost behavior. |
| Control over transition timing | Governed by Autoclass mechanism. | Explicitly configured with supported conditions. |
| Cost | Has its own pricing/rule model; evaluate carefully. | Storage, retrieval, operations, and transition costs per rules. |
| Compatibility | Check feature-combination restrictions. | Check compatibility with retention, versioning, and classes. |

When choosing, **do not enable Autoclass and expect manual `SetStorageClass` rules to behave as you want** if product rules restrict combining them. Verify compatibility before switching.

## 8. Minimum Storage Duration and Unexpected Billing Scenarios

### 8.1. Early Deletion Does Not Only Happen on DELETE Calls

Suppose a `NEARLINE` object is created and then replaced after 10 days. Since the class has a 30-day minimum requirement, the remaining shortfall can trigger an **early deletion charge**, even though the replacement occurred by uploading a new object.

Scenarios to check against pricing rules:

- Deleting an object before its minimum duration.
- Replacing an object version with a new one.
- Changing an object's storage class before the minimum period expires.
- Deleting object versions or soft delete policies causing retained data to incur extra storage charges.
- Using automated lifecycle rules whose age thresholds misalign with the class pricing model.

**Do not apply Archive to data that only lives for a few days**, no matter how low the per-GiB/month storage rate appears.

### 8.2. Notes on Versions and Soft Delete

When **Object Versioning** is enabled, replacing an object may create a **noncurrent version** instead of simply removing the old version. If **soft delete** is active, deleted data may still be retained for the configured recovery window and incur storage charges. Lifecycle rules must account for both live objects and noncurrent versions.

Example:

~~~text
products/item-1001.jpg
  generation 1001: old image, noncurrent
  generation 1002: current live image

If versioning is enabled:
  charges can apply across multiple versions,
  not just the size of the live image.
~~~

Versioning helps recover from overwrite mistakes in some scenarios, but it is neither free nor a substitute for a full backup plan. If compliance requires keeping objects immutable, evaluate retention/holds per requirements rather than relying solely on versioning.

### 8.3. Archive Can Still Be Read Online

When you need to restore Archive data, do not assume a multi-hour "offline restore" process as on some other platforms. However:

- Read volume may incur **retrieval charges**.
- High API operation counts can incur fees.
- Traffic sent to another region or the internet can generate transfer charges.
- Repeated reads should prompt checking whether to change classes or copy data to a serving class/location.

Do not mass-convert Archive data to Standard just for a small audit request; estimate the actual number of objects and bytes you need to read.

## 9. Hands-On with `gcloud storage`

These examples use the Google Cloud CLI, a test project, and illustrative bucket names. **Creating buckets or updating classes/lifecycle mutates real resources and may incur charges**. Only run them with proper permissions and approval; never test delete rules against production data.

### 9.1. Check Context and Buckets

~~~bash
# READ-ONLY: confirm active identity and selected project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: list buckets in the specified project.
gcloud storage buckets list \
  --project=retail-lab
~~~

The list command only displays resources the user is authorized to view. Not seeing a bucket does not mean that bucket does not exist.

### 9.2. Create a Regional Standard Bucket

~~~bash
PROJECT_ID="retail-lab"
BUCKET="retail-media-lab-unique-example"
LOCATION="asia-southeast1"

# WRITE: bucket name must be unique and valid; replace sample with an approved name.
gcloud storage buckets create "gs://$BUCKET" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access
~~~

**Uniform bucket-level access (UBLA)** enforces unified bucket-level IAM permissions instead of per-object ACLs; however, you still need to grant the proper roles and check public access prevention if data must not be public. Do not assume creating the bucket grants read access to end users or completes data protection policies.

If the name is already taken, pick another. Never place secrets, sensitive customer identifiers, or tokens in bucket or object names.

### 9.3. Inspect Location and Default Class

~~~bash
# READ-ONLY: inspect bucket metadata.
gcloud storage buckets describe "gs://$BUCKET" \
  --format="yaml(name,location,locationType,storageClass,autoclass)"

# READ-ONLY: list objects currently in the bucket.
gcloud storage ls "gs://$BUCKET/"
~~~

A new bucket may be empty, so an empty object listing is not an error. When validating location, compare **`location` and `locationType`** against your approved choice rather than inferring from the bucket name string.

### 9.4. Upload and Inspect an Object's Storage Class

Assuming the learner has a small local image `sample.jpg`:

~~~bash
# WRITE: upload a test object.
gcloud storage cp sample.jpg "gs://$BUCKET/products/sample.jpg"

# READ-ONLY: inspect object metadata.
gcloud storage objects describe "gs://$BUCKET/products/sample.jpg" \
  --format="yaml(name,size,storageClass,timeCreated,updated)"
~~~

If an object is created without specifying a separate storage class, its class typically comes from the **bucket's default storage class**. Always inspect the **object's** `storageClass` field, not just the bucket's default.

### 9.5. Change the Default Storage Class

~~~bash
# WRITE: affects the default class of new objects in a standard bucket.
gcloud storage buckets update "gs://$BUCKET" \
  --default-storage-class=NEARLINE

# READ-ONLY: verify the new default.
gcloud storage buckets describe "gs://$BUCKET" \
  --format="yaml(location,storageClass)"
~~~

Changing the default **does not convert existing objects' classes**. If the bucket has Autoclass enabled or other constraints, adjusting the class may be restricted; check configuration and policies first. To avoid unexpected charges, do not set `NEARLINE` as the default for new data that is routinely deleted or replaced after a few days.

### 9.6. Apply a Lifecycle Rule in the Lab

After creating `lifecycle.json` using the example in section 7.3 and carefully reviewing its contents:

~~~bash
# WRITE: update the test bucket's lifecycle rules.
gcloud storage buckets update "gs://$BUCKET" \
  --lifecycle-file=lifecycle.json

# READ-ONLY: inspect current lifecycle to confirm.
gcloud storage buckets describe "gs://$BUCKET" \
  --format="yaml(lifecycle)"
~~~

**Do not run this command to overwrite lifecycle settings on a production bucket without backing up the existing configuration and conducting a full review**: updating lifecycle rules replaces or modifies the active rule set. Lifecycle actions execute asynchronously; do not judge success merely by checking whether objects changed class a few seconds later.

### 9.7. Can Bucket Location Be Changed?

Do not treat bucket location as a field you can freely update with `gcloud storage buckets update`. If you need to move data to a different region/dual-region/multi-region, check **Google Cloud's bucket relocation capabilities at the time of implementation** or plan a migration/copy to a bucket in the new location.

A migration/relocation must check:

- Whether the tool supports the current **source location, target location, class, and bucket features**.
- Duration/object count, transfer fees, and application availability requirements during the move.
- IAM, retention, versioning, soft delete, default encryption, event notifications, and lifecycle rules.
- URIs used by applications and CI/CD; if the new bucket has a different name, configurations must be updated.
- Checksum verification plans, object version reconciliation, and cutover timing for access permissions.

Never delete the old bucket until data and applications are safely verified at the destination.

## 10. Real-World Scenario: Three Data Groups in a Retail System

Suppose an organization runs:

- **Cloud Run** serving the product API in `asia-southeast1`.
- **GKE** processing and transforming images.
- **Compute Engine** running report aggregation jobs.
- **Cloud SQL** storing order metadata.
- Requirements to control access and allocate costs by business unit.

The three data types have different characteristics:

| Data Group | Access Frequency | Retention Duration | Primary Risks |
| --- | --- | --- | --- |
| **Active product images** | Many requests per day. | May be updated/replaced frequently. | Image load latency, distribution cost, accidental deletion. |
| **Periodic reports** | Infrequent reads; many files may be downloaded together during audits. | Several months to over a year. | Retrieval fees on heavy reads, transitioning classes too early. |
| **Long-term archives** | Almost never accessed unless legally required. | Many years. | Residency/retention compliance, unauthorized deletion, long-term storage cost. |

### 10.1. Initial Proposal

**Product images group:**

~~~text
Bucket: retail-images-prod
Location: regional asia-southeast1 (if policy-compliant)
Default class: STANDARD
Consumers: Cloud Run / GKE / Cloud CDN where appropriate
~~~

Rationale: high read traffic; objects may be updated; need caching, public access controls, and proper service account permissions. For strict cross-region DR requirements, evaluate dual-region or a dedicated replication/recovery plan rather than staying regional alone.

**Reports group:**

~~~text
Bucket: retail-reports-prod
Location: regional per business and residency requirements
Class: STANDARD for new data; lifecycle to NEARLINE/COLDLINE
       after measuring access frequency and retention duration.
~~~

Rationale: new reports may be viewed often for a few weeks, while older reports are rarely touched. Class transition rules must align with minimum storage durations and deletion policies.

**Long-term archives group:**

~~~text
Bucket: retail-compliance-archive
Location: option approved by legal and security
Class: ARCHIVE or gradual lifecycle transition
Protection: retention / holds / audit and on-demand recovery
~~~

Rationale: rarely read, retained long-term. You must budget retrieval costs when records are requested and check minimum storage durations. Do not assume Archive automatically enforces non-deletable retention.

### 10.2. Why Consider Multiple Buckets?

Cloud Storage allows multiple storage classes in the same bucket, but separating buckets can help when:

- **Location requirements differ**: a bucket has only one location, so data required in another region needs another bucket.
- **Retention and permissions** differ sharply between public assets and compliance records.
- **Autoclass/lifecycle** needs different configurations per group.
- You want clean separation of ownership, budgets, monitoring, and release workflows.

Do not create one bucket per file or per user just for cost allocation. Base bucket boundaries on location, policies, lifecycle, permissions, ownership, and operability.

### 10.3. Routing Permissions and Data

~~~mermaid
flowchart TD
    SHOP["Cloud Run: shop API"] --> IMG["Images bucket: Standard / CDN"]
    ETL["GKE: image processing"] --> IMG
    REPORT["Compute Engine: report job"] --> RPT["Reports bucket: lifecycle"]
    RPT --> ARC["Colder object classes by age"]
    AUDIT["Restricted audit team"] --> COM["Archive bucket: Archive/retention"]
    IAM["Service accounts + IAM / policy"] -. "Permission scope" .-> IMG
    IAM -. "Permission scope" .-> RPT
    IAM -. "Permission scope" .-> COM
    OBS["Cloud Monitoring + Billing"] -. "Cost and access" .-> IMG
    OBS -. "Cost and access" .-> RPT
    OBS -. "Cost and access" .-> COM
~~~

Applications must be granted **least-privilege IAM roles** on the appropriate buckets/objects; Cloud SQL and other services continue to use their own credentials. To serve images publicly, design a dedicated delivery path (e.g., Cloud CDN/load balancer) and access policy rather than turning internal buckets public.

### 10.4. Upload, Class Transition, and Recovery Flow

1. Cloud Run/GKE uploads an object and records necessary metadata in Cloud SQL.
2. For frequently accessed data, objects stay in Standard; the system serves images via cache/CDN where appropriate.
3. For reports, lifecycle rules evaluate object age and conditions, transitioning classes when eligible.
4. For compliance records, retention governs how long data is held; Archive or other classes reflect access frequency and **do not replace deletion protection**.
5. When recovery is needed, operators verify identity, target data/versions, retrieval costs, and where restored outputs are written.
6. After a recovery request, evaluate whether to adjust the storage class or caching strategy if read frequency has changed.

## 11. Security and Required Policies

### 11.1. Bucket Location Is Not Access Control

Data sitting in the right region is still unsafe if IAM is overly broad. A production storage configuration needs:

- **Uniform bucket-level access** to standardize IAM instead of per-object ACLs.
- **Public Access Prevention** if the bucket must not be public, per organizational policy.
- **Dedicated service accounts** for Cloud Run/GKE/Compute Engine; never use a single account with write/delete permissions across all buckets.
- Monitoring for changes to IAM, lifecycle, retention, encryption, and data sharing.
- Considering **CMEK with Cloud KMS** when the organization needs key lifecycle control; the key's location must be compatible with the bucket per documentation.
- **Organization Policies** restricting allowed locations or public access settings where required.

Cloud Storage encrypts data at rest automatically under its service model; choosing CMEK is an **additional key-management decision**, not the only way data gets encrypted.

### 11.2. Recovering from Accidental Deletion

Distinguish among these mechanisms:

| Mechanism | Purpose | Does Not Replace |
| --- | --- | --- |
| Dual-/multi-region | Service-managed geographic redundancy. | Backups against accidental deletion or bad writes. |
| Object Versioning | Retains object versions when replaced/deleted as configured. | Retention policies or comprehensive recovery in all scenarios. |
| Soft delete | Retains deleted data for a configured recovery window. | Long-term immutable retention. |
| Retention policy / object holds | Prevents premature deletion or modification while active. | Application capacity redundancy or availability mechanisms. |
| Dedicated backup/replication | Recovers from data loss or corruption per separate targets. | Source IAM and security controls. |

**RPO** (maximum acceptable data loss) and **RTO** (recovery time) plans must be tested end-to-end from the application. Do not treat creating a dual-region bucket as enough to keep Cloud Run, Cloud SQL, and DNS working during a disaster.

### 11.3. Turbo Replication

In eligible **dual-region** configurations, Google Cloud offers **turbo replication** to improve replication targets compared to the default mode per service specifications. This decision can affect **pricing, RPO, and configuration limits**. If the business requires a very tight RPO between two regions:

1. Verify whether the chosen dual-region type supports turbo replication.
2. Check RPO/SLA and pricing in current documentation rather than inferring from the feature name.
3. Design applications to access data and handle errors per region.
4. Verify redundancy of services outside Cloud Storage.

Never promise "zero RPO" solely from enabling replication. Write acceptance, replication completion, and outage accessibility are distinct events.

## 12. Estimating Costs Before Choosing

### 12.1. Lifecycle Cost Model

~~~text
Estimated total storage cost ≈
    Storage charges by class, location, size, duration
  + Retrieval fees and API operation charges
  + Early deletion / class-change charges if applicable
  + Data transfer and client content delivery
  + Replication fees or add-on feature charges where applicable
  + Versioning, soft delete, retention, and unused data
  + Logging, monitoring, and related components
~~~

This is a **cost-categorization formula**, not an official price sheet. Each charge has specific units and rules; check **Cloud Storage pricing** for your actual location/class and reconcile against Billing reports.

### 12.2. Build a Data Table Before Deciding

| Object Group | Average Size | GETs/Month | Data Read Out/Month | Retention Duration | Class Under Consideration |
| --- | --- | --- | --- | --- | --- |
| Active images | Measured from bucket | High | High | Few months, replaced | Standard |
| Reports | Measured from bucket | Low, bursty | Moderate during audits | 6–18 months | Nearline/Coldline |
| Backups | Measured from bucket | Rare | Potentially huge on restore | Over 1 year | Coldline/Archive |
| Compliance data | Measured from bucket | Very rare | Hard to predict | Many years | Archive |

You do not have to lock in a final class before measuring behavior. You can start new data on Standard, monitor metrics, and adopt lifecycle rules or Autoclass at the right stage.

### 12.3. Scenarios That Break Cost Estimates

- Counting only live capacity while ignoring **noncurrent object versions** or soft-deleted data.
- Using Archive for objects routinely replaced before 365 days.
- Forgetting retrieval fees when running a job that reads back an entire backup.
- Running compute in one region with a bucket in a distant region without budgeting inter-region data transfer.
- Configuring lifecycle `age` conditions too aggressively, triggering unwanted class changes or early deletion charges.
- Ignoring **Cloud CDN cache misses**, invalidations, egress, and request processing fees.
- Omitting test costs, temporary data, and migration operations.

When costs diverge from expectations, break down **object counts, capacity by class, operation counts, retrieval, network transfer, and retention**, rather than looking only at the bucket's default class.

## 13. Troubleshooting When Location or Class Behaves Unexpectedly

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Cannot create bucket in chosen location. | Unsupported location, org policy restriction, bucket name taken, or missing IAM. | Read API error, `gcloud storage buckets create --help`, policies, and supported location list. |
| Bucket created, but location does not match needs. | Wrong `LOCATION` variable, multi-region name used instead of region, or dual-region misunderstanding. | `gcloud storage buckets describe`; plan relocation/migration instead of ad-hoc edits. |
| New object does not have the bucket's default class. | Client specified an explicit class or Autoclass is managing it. | Check object metadata, bucket Autoclass state, and upload tool behavior. |
| Changed default class, but old objects stayed unchanged. | Default only applies to new objects. | Check object metadata; apply lifecycle/transitions per plan. |
| Lifecycle has not transitioned class on schedule. | Lifecycle runs asynchronously; rule did not match `age`, class, or prefix; blocking policy. | Inspect lifecycle config, object metadata/age, and related logs if available. |
| Object deleted earlier than expected. | Overbroad Delete rule, overwrite, another lifecycle rule, or improper delete permission. | Check lifecycle, audit logs, versioning/soft delete, and retention. |
| Cannot delete object even past lifecycle age. | Retention policy, object hold, or another policy blocks it. | Inspect retention config, holds, and version states. |
| Coldline/Archive costs are high. | Retrieval, early deletion, operations, multiple versions, or transfer. | Cloud Billing, access patterns, and object lifecycle. |
| Remote users experience slow image loads. | Cache misses, inefficient app/proxy, network path, or suboptimal location. | Measure latency, CDN cache hit rate, DNS/TLS, transfer, and backend. |
| VM cannot read a bucket in the same region. | Missing IAM, token, DNS, Private Google Access/egress, or app bug. | Troubleshoot from API/network to authorization; do not blindly move the bucket. |

### 13.1. Six-Step Investigation Method

1. **Identify resources:** project, bucket name, location, locationType, and actual default class.
2. **Identify objects:** storage class, age, size, version, and update time of sample objects.
3. **Inspect policies:** IAM, public access, lifecycle, Autoclass, retention/holds, versioning, and soft delete.
4. **Inspect requests:** GET/LIST/PUT/DELETE, client identity, where the app runs, and operation counts.
5. **Correlate results and billing:** use collected API errors, logs, Billing data, and metrics.
6. **Test in non-prod:** validate impact on sample data with approval before modifying production buckets.

Do not treat a cost increase after moving to a colder class as proof of a billing bug; retrieval and lifecycle operation charges can raise total cost even when the base storage rate drops.

## 14. Exercises

### Exercise 1 — Choosing a Location

A system runs entirely in `asia-southeast1`, and data must remain in that exact region. Would you choose regional, dual-region, or multi-region? If the requirement changes so that data must be recoverable after a full-region outage, what conditions must be evaluated?

**Hint:** Regional first due to placement constraints; when DR is required, clarify whether a second region is permitted, and whether dual-region/backups meet RPO/RTO and cost targets.

### Exercise 2 — Choosing a Storage Class

Select a class for three objects:

1. A product image accessed continuously and replaced after one week.
2. A report that might be read once after 45 days and kept for six months.
3. A record rarely accessed that must be retained for five years.

**Hint:** Start by evaluating Standard, Nearline/Coldline, and Archive respectively; recalculate if actual access patterns differ or if retrieval/early deletion fees apply.

### Exercise 3 — Reading Metadata

Suppose a bucket's default class is `STANDARD`, yet an object inside it shows `COLDLINE`. What could have happened? State at least three possibilities and the commands to verify.

**Hint:** The client specified a class on upload, lifecycle transitioned it, or Autoclass managed it (if enabled). Use `gcloud storage buckets describe` and `gcloud storage objects describe`.

### Exercise 4 — Designing Lifecycle

A team wants new reports in Standard for 30 days, then Nearline until day 90, Coldline until day 365, and Archive afterward. Review the JSON in section 7.3, explain how `age` and `matchesStorageClass` interact, and explain why minimum duration must be checked.

### Exercise 5 — Investigating Archive Costs

The audit team requests downloading all very large Archive files to another region. What charges should be estimated beforehand? If the output must be analyzed multiple times during the month, should they keep reading directly from Archive every time?

**Hint:** Retrieval, operations, network transfer, retention duration, and location of the analytics copy; evaluate copying/moving data to a class/location suited for repeated access.

### Exercise 6 — Distinguishing Durability and Recovery

A developer accidentally deletes an object in a dual-region bucket. Does dual-region guarantee recovering the old version? Propose protection mechanisms beyond location.

**Hint:** Versioning, soft delete, retention/holds, independent backups as needed, and least-privilege access policies.

### Exercise 7 — Multi-Application Scenario

Cloud Run and GKE run in Singapore, Compute Engine generates monthly reports, and compliance data must be retained for seven years. Design **at least two buckets**, specifying location/class, lifecycle, access permissions, and cost metrics to monitor; explain why a single configuration should not be used for all data groups.

## 15. Production Readiness Checklist

| Item | Passing Criteria |
| --- | --- |
| **Ownership** | Designated owners for data, project, bucket, and cost allocation. |
| **Location** | Region/dual-region/multi-region fits workload, legal, and DR targets. |
| **Data residency** | Verified scope of location, replication, KMS, logs, backups, and auxiliary data. |
| **Storage class** | Selected based on access pattern, size, data age, and recovery needs. |
| **Default vs. object class** | Verified actual class of new/old objects rather than inferring from bucket default. |
| **Minimum duration** | Accounted for early deletion/replacement/transition fees (30/90/365 days per class). |
| **Lifecycle/Autoclass** | Chose one compatible strategy; rules reviewed and tested on sample data. |
| **Retention/Versioning** | Understands noncurrent version lifecycles, holds, soft delete, and recovery capabilities. |
| **Security** | Least-privilege IAM, UBLA, public access settings, encryption/KMS, and appropriate auditing. |
| **Networking** | Cloud Run/GKE/VMs reach APIs over proper paths without opening overly broad access. |
| **Performance** | Measured GET/PUT latency, throughput, cache hit rates, and cross-region data transfer. |
| **Costs** | Estimated storage, retrieval, operations, transfer, retention, versions, and replication. |
| **Operations** | Monitoring, Billing alerts, recovery runbooks, and migration plans in place. |
| **Validation** | Tested uploads, downloads, metadata reads, class transitions, and restores against real requirements. |

## 16. Official Documentation and Key Takeaways

Features, dual-region support rules, Autoclass behavior, minimum storage durations, and pricing are subject to change. Before deploying or automating at scale, consult the official documentation:

- [Cloud Storage locations](https://cloud.google.com/storage/docs/locations)
- [Cloud Storage classes](https://cloud.google.com/storage/docs/storage-classes)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Create a bucket](https://cloud.google.com/storage/docs/creating-buckets)
- [Bucket relocation](https://cloud.google.com/storage/docs/bucket-relocation/overview)
- [Object Lifecycle Management](https://cloud.google.com/storage/docs/lifecycle)
- [Autoclass](https://cloud.google.com/storage/docs/autoclass)
- [Object Versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Soft delete](https://cloud.google.com/storage/docs/soft-delete)
- [Retention policies and Bucket Lock](https://cloud.google.com/storage/docs/bucket-lock)
- [Uniform bucket-level access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Dual-region turbo replication](https://cloud.google.com/storage/docs/availability-durability)
- [gcloud storage reference](https://cloud.google.com/sdk/gcloud/reference/storage)

**Key Takeaway:** **Bucket location** answers where data is stored geographically and under which redundancy model; **storage class** answers access frequency and lifecycle storage cost. Only by properly combining those two decisions with IAM, retention, lifecycle/Autoclass, recoverability, networking, and actual Billing data can an operations team achieve a Cloud Storage design that is both business-aligned and verifiable for security, reliability, and cost.

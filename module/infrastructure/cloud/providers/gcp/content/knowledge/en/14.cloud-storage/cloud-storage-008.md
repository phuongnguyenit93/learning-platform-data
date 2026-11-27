# Object Encryption and Choosing Bucket Keys in Cloud Storage

> **Chapter:** Cloud Storage  
> **Lesson:** Object Encryption and Choosing Bucket Keys  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore how to organize projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, and databases. When deploying Java systems, operators must choose services, protect resources, automate releases, and monitor reliability and costs. A common question when storing invoices, images, backups, or application artifacts in **Cloud Storage** is: **Which key encrypts the data, who is authorized to use that key, and what happens if the key becomes unavailable?**

Cloud Storage **automatically encrypts customer content at rest (encryption at rest)**. Organizations can rely on **Google default encryption**, actively manage **customer-managed encryption keys (CMEK)** via Cloud Key Management Service (Cloud KMS), or supply **customer-supplied encryption keys (CSEK)** per request. Some use cases encrypt data at the application layer **before uploading**. These options carry very different responsibility boundaries, costs, and operational consequences.

**Core principle:** Choosing encryption keys must be grounded in **key control requirements, compliance, recoverability, data residency, workload integration, and organizational risk tolerance**. CMEK does not by itself make a bucket private; IAM, public access prevention, Uniform bucket-level access, lifecycle rules, retention, and key protection remain essential layers.

Project, bucket, key ring, and CryptoKey names in this lesson are illustrative examples only. Any resource-mutating commands must run in an **authorized sandbox** with cost estimates and a rollback plan.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **encryption in transit**, **encryption at rest**, and **client-side encryption** when an application uploads objects.
2. Compare **Google default encryption**, **CMEK**, **CSEK**, and client-side encryption by who manages the keys, compatibility, and data-loss risks.
3. Distinguish a bucket's **default KMS key** from the **actual key used on an object**, and understand precedence when an upload specifies its own key.
4. Choose the right **Cloud KMS key ring location**, key type, protection level, and key-hosting project layout.
5. Identify the **Cloud Storage service agent** and grant `roles/cloudkms.cryptoKeyEncrypterDecrypter` properly on the key.
6. Configure, inspect, or clear **default CMEK** on a bucket via the Console and `gcloud storage`.
7. Explain **key rotation**, **key replacement**, **object rewrite**, versioning, retention, and the consequences when a key is disabled or destroyed.
8. Use **encryption enforcement rules** to require or restrict encryption types for new objects rather than relying solely on defaults.
9. Design monitoring, troubleshooting for `403`/key-unavailable errors, and cost, backup, and DR planning for critical data.

## 2. Distinguishing Data, Keys, and Access Permissions

### 2.1. Three Distinct Protection Layers

~~~mermaid
flowchart LR
    U["Java Application<br/>Cloud Run / GKE / VM"] --> T["TLS/HTTPS<br/>Encryption in transit"]
    T --> S["Cloud Storage API<br/>IAM + bucket policy"]
    S --> E["Encryption at rest<br/>Google-managed / CMEK / CSEK"]
    E --> O["Object payload<br/>encrypted at rest"]
    K["Cloud KMS key + service agent IAM"] -. "CMEK when selected" .-> E
~~~

- **TLS/HTTPS:** protects data in transit over the network; not the object's at-rest key choice.
- **IAM / bucket authorization:** determines whether a principal is allowed `storage.objects.get`, `storage.objects.create`, or other operations.
- **Encryption at rest:** protects data stored on infrastructure; Cloud Storage performs encryption for objects.
- **Client-side encryption:** the application encrypts data **before sending** it to Cloud Storage, after which Cloud Storage still applies server-side encryption.

Someone lacking appropriate IAM permissions **cannot read an object** simply because Cloud Storage uses a Google-managed key. Conversely, someone holding IAM to read a CMEK-encrypted object also needs Cloud Storage **to be able to decrypt it** via the service agent's permissions and the CryptoKey's state.

### 2.2. Object Encryption Is Not Account Credentials

| Concept | Purpose | Example |
|---|---|---|
| **Google identity / service account** | Identity of a user or workload | `orders-api@project.iam.gserviceaccount.com` |
| **IAM role on bucket** | Authorizes reading/writing objects | `roles/storage.objectViewer` |
| **Cloud Storage service agent** | Service identity acting on behalf of Cloud Storage to use CMEK | Service agent of the project owning the bucket |
| **Cloud KMS CryptoKey** | Managed key protecting stored data | `projects/key-project/locations/asia-southeast1/keyRings/app/cryptoKeys/invoices` |
| **CryptoKeyVersion** | Key material version used for encryption/decryption | Primary version and older versions |
| **Bucket default KMS key** | Default key for **newly written objects** | A bucket configuration property |
| **Object encryption metadata** | Information on the method/key used when the object was written | `kmsKeyName` on a CMEK object |

**Do not confuse the Google Cloud service account running your Java API with the Cloud Storage service agent.** With CMEK, Cloud Storage calls Cloud KMS using the **service agent of the project containing the bucket**, not the email of the user who uploaded the object.

## 3. Four Data Encryption Options

### 3.1. Comparison Table

| Option | Who Manages Server-Side Keys? | How Applied | Benefits | Primary Trade-offs |
|---|---|---|---|---|
| **Google default encryption** | Google manages default keys | Automatic for Cloud Storage data | Simple; minimal key-management overhead | Less control over key lifecycle and usage |
| **CMEK** | Customer manages a Cloud KMS CryptoKey; Cloud Storage encrypts data | Bucket default or per object | Control over key IAM, rotation, audit, lifecycle | Depends on KMS/service agent; cost, quotas, decryption-loss risk |
| **CSEK** | Customer generates and keeps **raw AES-256 keys**, sending one with each request | **Per object**, cannot be bucket default | Fits organizations with external key management outside Cloud KMS | Must store and supply exact key every time; losing the key loses data |
| **Client-side encryption** | Application/client encrypts before upload | Encrypts payload before reaching Cloud Storage | Client controls plaintext end-to-end | Must build key management, format, rotation, search/indexing, and recovery |

Cloud Storage still encrypts data **server-side** even when the application already encrypted client-side. Client-side encryption is therefore an **additional** layer, not a way to "disable" Cloud Storage at-rest encryption.

### 3.2. Google Default Encryption: The Baseline Option

On new buckets without CMEK or CSEK specified, Cloud Storage uses **Google default encryption** for stored data. This fits well when there is no requirement for the customer to directly own key lifecycles.

No Cloud KMS CryptoKey creation, service agent role grants, or key headers in code are needed. However, you still need to:

- Restrict read/write access via IAM and Uniform bucket-level access.
- Prevent unintended public objects using appropriate policies.
- Protect objects with soft delete, retention, Object Versioning, or backups as required.
- Configure logging, policy-compliant data access auditing, lifecycle rules, and billing alerts.

**Google default encryption does not mean objects are public**, nor does it mean data recovers automatically after accidental deletion.

### 3.3. CMEK: Active Key Governance with Cloud KMS

With a **customer-managed encryption key**, Cloud Storage calls Cloud KMS to use a **symmetric encryption** key managed by your organization. Your organization can configure:

- **Key rings**, **CryptoKeys**, key versions, and key rotation.
- Key location scope matching the bucket location.
- Permissions for service agents authorized to use the key.
- Protection levels such as **software**, **Cloud HSM**, or **Cloud EKM** where supported.
- Audit logs, separation-of-duties policies, and controlled disable/destroy workflows.

CMEK is **server-side encryption**: when an authorized principal reads an object, Cloud Storage **decrypts automatically** as long as the service agent retains permission and the key remains enabled. Clients **do not call Cloud KMS directly** during normal object downloads.

### 3.4. CSEK: Managing Raw Keys Yourself

With a **customer-supplied encryption key**, the client supplies an AES-256 key in the appropriate header/API/CLI option **when writing or reading an object**. Cloud Storage does not store the raw key to hand back later; the customer must retain and provide the key whenever needed.

Limitations to remember:

- **CSEK cannot be configured as a bucket's default encryption key.**
- You cannot use the Console to upload objects with CSEK or download CSEK-protected objects.
- Some integrated products do not support CSEK-encrypted objects (such as certain Dataflow or Storage Transfer Service flows).
- If you lose a CSEK, Google cannot "recover the key" to restore access to your data.
- Never write CSEK values into source code, shell history, logs, tickets, or exposed environment variables.
- You can **rewrite** an object to rotate its CSEK or migrate to CMEK while the old key is still available.

**Note:** **Cloud Storage** CSEK remains a documented supported option; do not confuse it with deprecation notices for **Compute Engine CSEK**, as those are two distinct integrations.

### 3.5. When Is Client-Side Encryption Needed?

This model fits when requirements demand **never exposing plaintext to the cloud provider during server-side processing** or enforcing custom cryptographic controls. However, it reduces direct server-side processing, previews, indexing, transformations, and recovery options. The system must manage:

- Key generation, rotation, backup, key escrow, or HSMs.
- Ciphertext framing, authentication tags, nonces/IVs, and metadata.
- Decryption authorization for legitimate applications.
- Recovery workflows when older key versions age out.
- Backup and restore testing.

**Never invent your own encryption algorithm.** Use standard libraries and a key-management plan approved by security specialists.

## 4. Bucket Default KMS Key vs. Per-Object Key

A bucket is not "re-encrypted all at once" merely because an administrator changes its default encryption key. The key decision happens at **object write time**.

~~~mermaid
flowchart TD
    W["Object upload / copy / rewrite request"] --> X{"Does the request specify<br/>a separate encryption key?"}
    X -->|Yes| O["Use specified key<br/>if encryption type is allowed"]
    X -->|No| B{"Does bucket have default CMEK?"}
    B -->|Yes| K["Cloud Storage uses default CMEK"]
    B -->|No| G["Google default encryption"]
    O --> E["Check IAM / key availability<br/>and encryption enforcement"]
    K --> E
    G --> E
    E --> R["Object saved with valid method"]
~~~

### 4.1. Application Rules

| Case | Encryption Method for New Object |
|---|---|
| Bucket has no default CMEK; request specifies no key | Google default encryption |
| Bucket has default CMEK; request specifies no key | Bucket's default CMEK |
| Bucket has default CMEK; request specifies a **different CMEK** | **Request's** CMEK, if valid |
| Bucket has default CMEK; request supplies a **CSEK** | **Request's** CSEK, if valid |
| Bucket enforces encryption allowing CMEK only | New objects must use CMEK; other methods are rejected |
| Admin changes default CMEK from A to B | **New** objects use B; **existing** objects keep old key until rewritten |

An object uses **one server-side encryption method at a time**. Internally Cloud Storage performs multi-layered encryption, yet you should never think of an object as simultaneously stored under "CMEK + CSEK" with two customer keys.

### 4.2. Changing Default CMEK Does Not Affect Existing Objects

Example:

~~~text
Day 01:
  Bucket invoices has default CMEK key-A
  → upload invoices/001.pdf → key-A

Day 10:
  Change bucket default to key-B
  → upload invoices/002.pdf → key-B

After Day 10:
  invoices/001.pdf is still protected by key-A
  invoices/002.pdf is protected by key-B
~~~

To move `invoices/001.pdf` from A to B, you must **rewrite the object** using a supported mechanism. Destroying `key-A` right after changing the bucket default can render existing objects **unreadable**. With Object Versioning or soft delete, **older generations** may also still reference `key-A`.

### 4.3. CMEK Does Not Encrypt All Metadata with That Same CMEK

Cloud Storage uses CMEK to protect **object data** and certain integrity fields like CRC32C/MD5 under its product model; **object names and most metadata** remain encrypted via Google-managed server-side encryption.

Implications:

- Disabling or destroying a key does not "wipe out the list of object names."
- Principals with sufficient permissions can still view certain metadata or delete objects per policy.
- Avoid putting sensitive data into **bucket names, object names, metadata, or labels** solely because the object payload uses CMEK.
- If names and metadata must also be hidden at the application level, design appropriate client-side naming or encryption schemes.

## 5. Choosing a Cloud KMS Key for a Bucket

### 5.1. Parts of a Cloud KMS Resource Name

~~~text
projects/KEY_PROJECT_ID
  /locations/asia-southeast1
  /keyRings/storage-data
  /cryptoKeys/invoices
~~~

- The **key-hosting project** can **differ** from the bucket-hosting project to enforce separation of duties.
- The **location** of the key ring must **match the bucket's location** per Cloud Storage rules.
- The **key ring** groups CryptoKeys in that location.
- The **CryptoKey** is the logical key; Cloud KMS maintains key versions and a primary version.

Never use **asymmetric signing**, HMAC, or public keys for Cloud Storage CMEK; this integration requires an appropriate **symmetric encryption key**.

### 5.2. Co-Location Requirement

| Cloud Storage Bucket Location | Cloud KMS Key Ring Location |
|---|---|
| Single region `asia-southeast1` | `asia-southeast1` |
| Single region `us-east1` | `us-east1` |
| Multi-region `US` | `us` (exact matching location code) |
| Configurable dual-region of two valid regions with location code `ASIA` | `asia` |
| Predefined dual-region `NAM4` | `nam4` |

**Do not assume** either member region of a dual-region can host the key: for dual-regions, the KMS location must **match the bucket's location code**, not one individual member region. If regions/locations mismatch, configuration or object writes will be rejected.

A key ring in another location cannot simply "change region"; you must create a new key ring/key in the matching location and plan default updates and object rewrites per documentation.

### 5.3. Software, HSM, and External Key Management

| Key Protection | Advantages | Trade-offs |
|---|---|---|
| **Cloud KMS software key** | Easy to use, simple operations, API/rotation/audit | Key policy and management live within Google Cloud |
| **Cloud HSM key** | Key material protected inside HSMs per service assurances | Different pricing, quotas, and provisioning constraints; budget carefully |
| **Cloud EKM key** | Key material and certain security decisions stay in an external key manager outside Google Cloud | Depends on external key manager availability, connectivity, latency, and policies |
| **Autokey CMEK** | Automatically provisions and binds keys/roles for resources per integration | Requires proper org/project setup; does not cover every per-object workflow |

CMEK with Cloud KMS **Autokey** reduces manual bucket key setup. However, **Autokey does not auto-create separate keys per object**; objects normally use the bucket's configured default CMEK unless a request specifies a per-object key.

### 5.4. Naming and Ownership Governance

Suggested convention:

~~~text
Key project:  sec-keys-prod
Key ring:     storage-asia-southeast1
CryptoKey:    invoices-prod
Bucket:       gs://retail-invoices-prod-EXAMPLE-UNIQUE
Owner:        Security Key Management
Consumer:     Cloud Storage service agent of the bucket project
Data owner:   Finance / Orders Platform
Recovery:     Backup owner + incident runbook
~~~

Names above are examples, not real resources. Maintain:

- Separate key owners and data owners; key creation/editing rights separated from object read access.
- Rotation schedules, retention rules, and disable/destroy governance.
- An inventory of buckets/objects depending on each key.
- Key locations aligned with data residency.
- Alerts on key actions, IAM grants, KMS request failures, and billing.

## 6. IAM: Three Principals You Must Not Confuse

### 6.1. Users or Workloads Reading/Writing Objects

Java apps on Compute Engine, GKE, or Cloud Run use a **runtime service account** with IAM permissions on the bucket. For example, an invoicing upload service can use a role restricted to **object creation** on the bucket per product rules.

### 6.2. Cloud Storage Service Agent Using CMEK

To let Cloud Storage encrypt/decrypt objects with CMEK, grant **`roles/cloudkms.cryptoKeyEncrypterDecrypter`** on the CryptoKey to the **service agent** belonging to the **bucket-hosting project**.

~~~mermaid
flowchart TD
    J["orders-api runtime service account"] -->|"storage.objects.create/get via IAM"| S["Cloud Storage bucket<br/>in OBJECT_PROJECT_ID"]
    S --> A["Cloud Storage service agent<br/>of OBJECT_PROJECT_ID"]
    A -->|"cloudkms.cryptoKeyVersions.useToEncrypt/Decrypt"| K["Cloud KMS CryptoKey<br/>in KEY_PROJECT_ID"]
    T["Security team"] -. "Manages key and roles" .-> K
~~~

**When calling `storage.objects.get`, the application user does not normally need direct `roles/cloudkms.cryptoKeyDecrypter`** on the KMS key. Cloud Storage uses its service agent to decrypt, while the user's bucket IAM governs whether they may read the object. This avoids granting KMS roles to hundreds of app accounts.

### 6.3. Cloud KMS Administrators

Anyone creating CryptoKeys or editing key IAM needs appropriate KMS permissions on the **key project**, such as permissions in Cloud KMS Admin. Never grant `roles/owner` on the entire key project just to wire up one bucket key.

### 6.4. Inspecting the Service Agent

Command to read/initialize the service agent if it does not yet exist:

~~~bash
gcloud storage service-agent --project=OBJECT_PROJECT_ID
~~~

Within a project, Cloud Storage creates and manages its own service agent; **never manually create an arbitrary service account and treat it as the "Cloud Storage service agent."** The exact syntax and identity come from the command above or Cloud Storage Settings → Project Access.

**Note:** If the service agent does not exist yet, fetching the service agent may **initialize it**. Therefore, do not treat this command as 100% read-only on a brand-new project.

## 7. Lab A — Inspecting Encryption Settings Without Modifying Data

**Environment:** a sandbox project with an existing bucket where the learner has view permissions. No key creation or uploads needed.

### 7.1. Verify Account and Bucket

~~~bash
gcloud auth list
gcloud config get-value project

gcloud storage buckets describe gs://BUCKET_NAME
~~~

Check `location`, `storageClass`, default encryption, Uniform bucket-level access, and protection settings visible under your permissions.

### 7.2. Inspect the Default KMS Key

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(default_kms_key)"
~~~

If `default_kms_key` is empty/absent, the bucket generally has no **default CMEK**. However, **this does not prove every object is Google-managed**, since individual objects could have been uploaded with a per-object CMEK or CSEK.

### 7.3. Inspect Object Encryption Metadata

~~~bash
gcloud storage objects describe gs://BUCKET_NAME/OBJECT_NAME
~~~

Look for key fields such as `kms_key`/`kmsKeyName` depending on CLI/API output formatting. When an object uses CMEK, the CryptoKey name appears in metadata. With CSEK, key-related metadata/hashes appear—**never the raw key itself**.

Sufficient permissions are required to read metadata; `describe` failing on an object when your account lacks read permissions is not proof the object does not exist.

### 7.4. Comprehension Questions

1. Does the bucket have a default CMEK?
2. If so, in which project and location does the key reside?
3. Does the selected object use that default key or a different key?
4. Do objects created before changing the bucket's default key need to be rewritten?
5. If an application account lacks IAM read permissions on the object while the Cloud Storage service agent retains KMS permissions, can the application download the object?

## 8. Lab B — Preparing a Cloud KMS Key for a Bucket

**Commands in this section modify real resources and may incur charges.** Run only with authorization on **OBJECT_PROJECT_ID** and **KEY_PROJECT_ID** and a cleanup plan; never run in production without approval workflows.

### 8.1. Step 1: Check the Bucket Location

Suppose the bucket was created in `asia-southeast1`. First run `gcloud storage buckets describe` to **confirm** the actual location; never guess from the bucket name.

### 8.2. Step 2: Create the Key Ring and CryptoKey

~~~bash
# Requires permissions to create key rings / keys in KEY_PROJECT_ID.
gcloud kms keyrings create storage-data \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1

# Create a symmetric key for encryption.
gcloud kms keys create invoices \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1 \
  --keyring=storage-data \
  --purpose=encryption
~~~

Once created, the CryptoKey resource name takes the form:

~~~text
projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/invoices
~~~

**Do not treat deleting key rings as a routine lab cleanup step.** Cloud KMS key rings and keys follow different lifecycle rules from VMs or buckets; key material and versions must be managed per policy. Name them clearly and avoid using shared key projects for labs without approval.

### 8.3. Step 3: Authorize the Cloud Storage Service Agent

Google Cloud CLI convenience command:

~~~bash
gcloud storage service-agent \
  --project=OBJECT_PROJECT_ID \
  --authorize-cmek=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/invoices
~~~

This grants the required encrypt/decrypt permissions to the service agent on the key; the caller needs **IAM edit permissions on the CryptoKey**. If you lack permission, ask a KMS admin to grant `roles/cloudkms.cryptoKeyEncrypterDecrypter` on that **exact key** to the verified service agent email.

Never grant KMS permissions to `allUsers`, `allAuthenticatedUsers`, or all developers. Scope permissions to the **CryptoKey** rather than granting roles across the entire key project unless explicitly justified.

### 8.4. Step 4: Verify the KMS Resource

~~~bash
gcloud kms keys describe invoices \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1 \
  --keyring=storage-data

gcloud kms keys get-iam-policy invoices \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1 \
  --keyring=storage-data
~~~

Verify the policy includes the service agent principal and proper role, the key has an **enabled primary version**, and the location matches. Never assume holding Storage Admin grants permission to edit IAM on a key in another project.

## 9. Lab C — Setting and Verifying a Bucket's Default CMEK

### 9.1. Setup via Google Cloud Console

1. Open **Cloud Storage → Buckets** and select the right sandbox bucket.
2. Go to **Configuration → Protection → Edit encryption** (or the corresponding menu label).
3. Under **Default encryption key type**, choose **Cloud KMS key**.
4. Select the prepared key matching the **bucket location** and confirm service agent permissions.
5. Review expected impact, save changes, and read back the bucket configuration.

### 9.2. Setup via `gcloud`

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --default-encryption-key=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/invoices
~~~

Read back:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(default_kms_key)"
~~~

If successful, the bucket uses that CryptoKey for **newly created objects** whenever requests do not specify another key and encryption enforcement permits it.

### 9.3. Create a New Test Object

Non-sensitive sample file:

~~~bash
printf "Cloud Storage CMEK lab\n" > cmek-test.txt

gcloud storage cp cmek-test.txt \
  gs://BUCKET_NAME/labs/cmek-test.txt

gcloud storage objects describe \
  gs://BUCKET_NAME/labs/cmek-test.txt
~~~

Inspect object metadata and confirm the key actually used. When a bucket has a default CMEK and the service agent is authorized, uploads normally use the default key.

### 9.4. Specify a Separate CMEK per Object

When one object needs a different key, upload with:

~~~bash
gcloud storage cp cmek-test.txt \
  gs://BUCKET_NAME/labs/special-object.txt \
  --encryption-key=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/KEY_FOR_SPECIAL_OBJECT
~~~

This works only if `KEY_FOR_SPECIAL_OBJECT` **already exists**, has a valid primary version, is in a compatible location, and authorizes the service agent. It demonstrates that **a per-object key overrides the default key**.

### 9.5. Clear Default KMS Key to Return to Google-Managed for Future Objects

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --clear-default-encryption-key
~~~

This **updates bucket configuration** rather than decrypting or re-encrypting existing data. Prior objects stay on CMEK until rewritten. If the bucket has **encryption enforcement** blocking Google default encryption, creating new objects under Google-managed encryption may be blocked; check policies first.

**Do not confuse clearing default CMEK with disabling the CryptoKey.** Clearing the default only affects future writes; disabling the key can block reads of existing objects and cause outages.

## 10. Encryption Enforcement: Restricting Allowed Methods on a Bucket

Setting a **default CMEK** alone does not guarantee *every new object* uses CMEK, because a client request can still pass a CSEK or a different CMEK. Cloud Storage also supports bucket-level **encryption enforcement rules** to allow or restrict encryption methods when **creating new objects**.

### 10.1. Three Types That Can Be Restricted

| Type | Config File Field | Restriction Values |
|---|---|---|
| Google default encryption | `gmekEnforcement` | `FullyRestricted` or `NotRestricted` |
| Customer-managed CMEK | `cmekEnforcement` | `FullyRestricted` or `NotRestricted` |
| Customer-supplied CSEK | `csekEnforcement` | `FullyRestricted` or `NotRestricted` |

`FullyRestricted` blocks creating objects with that method. `NotRestricted` allows it. At least **one** encryption method must remain allowed.

Enforcement applies to object-creation operations such as **upload, copy, compose, and restoring soft-deleted objects** per service rules; **it does not automatically alter encryption on existing objects**.

### 10.2. Example CMEK-Only Bucket Policy

Create this file **only in a lab environment**, without placing secrets in a repo:

~~~json
{
  "gmekEnforcement": { "restrictionMode": "FullyRestricted" },
  "cmekEnforcement": { "restrictionMode": "NotRestricted" },
  "csekEnforcement": { "restrictionMode": "FullyRestricted" }
}
~~~

Save the example as `encryption-enforcement.json`, then apply it:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --encryption-enforcement-file=encryption-enforcement.json
~~~

**This action is strictly illustrative of configuration syntax.** Before applying in production, audit all jobs, pipelines, client libraries, Transfer Service jobs, copies, and how they select keys. On a CMEK-only bucket, uploads without an explicit key must have a valid **default CMEK**; non-compliant object-creation attempts will fail.

**Practical notes:**

- After updating, configuration changes may take some time to take effect (documentation notes up to roughly **two minutes**).
- On a bucket with a default CMEK configured, Cloud Storage does not allow restricting **both CMEK and CSEK** per documented limits without first clearing the default key.
- Blocking Google default encryption **does not automatically migrate existing objects to CMEK**.
- Do not block CSEK while business workflows still depend on it without a migration plan.

### 10.3. Default vs. Enforcement Answer Two Different Questions

- **Default KMS key:** "If the client specifies nothing, which key should Cloud Storage use for new objects?"
- **Encryption enforcement:** "Which encryption methods are **permitted** for creating objects in this bucket?"

For compliance mandates requiring CMEK on all new objects, combining **default CMEK + CMEK-only enforcement** is a clean pattern. Still, auditing existing objects requires an inventory and planned rewrites.

## 11. Rotation, Replacement, and Re-Encryption

### 11.1. Rotating a Cloud KMS CryptoKey

Cloud KMS can generate a new **CryptoKeyVersion** and promote it to **primary**. When Cloud Storage performs subsequent new encryption writes with **the same CryptoKey**, it uses the new primary version per service behavior.

~~~text
Day 01:
  CryptoKey invoices
  primary version = 1
  object-A is protected by version 1

Day 90:
  CryptoKey invoices rotated
  primary version = 2
  object-B uploaded after rotation → version 2

Object-A:
  still depends on version 1 unless rewritten
~~~

**Rotation does not automatically re-encrypt existing objects.** Version 1 must remain available to read `object-A`. Never disable or destroy older versions merely because a new version became primary.

### 11.2. Key Replacement Means Switching CryptoKeys

If the organization migrates from `key-A` to `key-B`:

1. Identify every bucket using `key-A` as default.
2. Create `key-B` in a compatible location and grant the role to the right service agents.
3. Update bucket defaults to `key-B` and update any clients specifying `key-A` per upload.
4. Inventory all objects and generations still using `key-A`.
5. **Rewrite** target objects to `key-B`, respecting generation/concurrency preconditions and retention policies.
6. Verify metadata and perform real test downloads with an authorized identity.
7. Only after confirming zero remaining dependencies should you consider disabling old versions under change/retention governance.

For millions of objects, use **Storage Batch Operations** supporting re-encryption by prefix or manifest. Budget for runtime, API operations, rewrite charges, and result reconciliation.

### 11.3. Rewriting a Specific Object

Illustrative command in a sandbox:

~~~bash
gcloud storage objects update gs://BUCKET_NAME/labs/cmek-test.txt \
  --encryption-key=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/NEW_KEY
~~~

Although named `objects update`, changing the encryption key performs an **object rewrite**. It is not a pure metadata edit.

To move an object back to the bucket's current default method (or Google default if no default CMEK is set):

~~~bash
gcloud storage objects update gs://BUCKET_NAME/labs/cmek-test.txt \
  --clear-encryption-key
~~~

If bucket enforcement disallows the target method, the rewrite will be rejected. Never run this on production objects under retention locks or holds without checking constraints.

### 11.4. How Versioning, Soft Delete, and Retention Affect Migration

| Mechanism | Impact on Rewrite/Rotate |
|---|---|
| **Object Versioning** | Older generations may remain encrypted under the **old key**; manage noncurrent versions too |
| **Soft delete** | Older copies may remain within their retention window; they do not vanish immediately on rewrite |
| **Retention policy / object retention** | May restrict changes or deletions until the committed period expires |
| **Object holds** | Can block deletion/replacement per supported semantics |
| **Lifecycle rules** | Can clean up old generations once eligible; test carefully to prevent accidental deletion |
| **Nearline/Coldline/Archive** | Rewrites/copies can incur request or early deletion charges if before minimum duration |

**Audit goal:** Do not stop at seeing live objects on `key-B`; hunt down **old generations, soft-deleted objects, backups, and copies in other buckets** still tied to `key-A` before destroying any key.

## 12. When a KMS Key Is Disabled, Destroyed, or Loses Permissions

### 12.1. Disable vs. Destroy

| Action | Primary Impact | Recoverability |
|---|---|---|
| Clear default CMEK on bucket | New writes may fall back to Google default if enforcement allows | Does not alter existing data |
| Revoke service agent's `cryptoKeyEncrypterDecrypter` IAM | Cloud Storage can no longer encrypt/decrypt with that key | Restorable by re-granting the exact role |
| **Disable CryptoKeyVersion** | Objects relying on that version cannot be read or rewritten | Can be **re-enabled** if not destroyed |
| **Destroy CryptoKeyVersion** | Data still relying on that version may **permanently lose decryptability** | Plaintext cannot be recovered from Cloud Storage alone |
| No valid primary version | Uploads/copies/rewrites requiring encryption with that key fail | Rotate or enable a valid primary version |
| Cloud EKM / external key manager unavailable | Operations may fail even while storage itself is healthy | Depends on restoring external key manager and connectivity |

**Critical consequence:** Destroying a key does not make Cloud Storage delete the objects or stop billing for storage. Objects can **continue existing and accruing storage charges** even though their contents can never be decrypted.

### 12.2. Disabling a Key Is Not a Routine Cleanup Action

In live environments:

- Use **disable** only under an approved incident response or access revocation procedure.
- Key/IAM changes may have **propagation delay**, so instant blocking of every request is not guaranteed.
- Monitor upload/download/compose/rewrite errors and application impact.
- When recovering, verify both service agent permissions and key version state before retrying.
- For **destroy**, require multi-party approvals, dependency scans across objects, and verified backup/restore procedures.

### 12.3. Why Key Loss Breaks Apps That Do Not Manage Keys

Suppose the Java Orders API holds `storage.objects.get` on the bucket. The key resides in a separate security project and a KMS admin accidentally disables it. The API still authenticates and passes bucket IAM, yet **Cloud Storage can no longer decrypt the payload**, so the app gets errors. Investigation must inspect **key state and service agent IAM**, rather than trying to fix it by granting `roles/storage.admin` to the API.

## 13. Real-World Scenario: Bucket Storing PDF Invoices

### 13.1. System Context

Retailer `RetailOne` deploys:

- **Cloud Run Java Orders API** in project `retail-app-prod`.
- **Cloud SQL** storing order records.
- **Cloud Storage** bucket `gs://retail-invoices-prod-EXAMPLE-UNIQUE` holding PDF invoices.
- **Key project** `retail-security-keys` managed by the Security team.
- Bucket placed in `asia-southeast1`, with key ring in the same location.
- FinOps wants cost estimates across Cloud KMS, Storage operations, and retention.

~~~mermaid
flowchart LR
    API["Java Orders API<br/>Cloud Run runtime identity"]
    API -->|"storage.objects.create / get"| B["Cloud Storage bucket invoices"]
    B -->|"service uses CMEK"| SA["Cloud Storage service agent"]
    SA --> K["CryptoKey invoices-prod<br/>KMS location asia-southeast1"]
    SEC["Security team"] -. "Manages rotation + key IAM" .-> K
    FIN["FinOps"] -. "Storage cost and retention reports" .-> B
    FIN -. "KMS usage/costs" .-> K
~~~

### 13.2. Recommended Design

1. **Data owner** defines invoice classification, retention, and recovery/compliance requirements.
2. **Security** creates the key in a dedicated project in the matching bucket location and configures key lifecycle rules.
3. The **Cloud Storage service agent** of `retail-app-prod` receives `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the CryptoKey.
4. The **Orders API service account** holds only required object create/read permissions on the bucket—never Cloud KMS Admin.
5. The bucket configures default CMEK and, if compliance requires, **CMEK-only encryption enforcement**.
6. Configure Uniform bucket-level access, public access prevention, backups/soft delete/retention, and logging appropriately.
7. Upon deployment, the API uploads invoices and logs generation/checksum, request IDs, and errors.
8. During key rotation, test both new and old objects; if migrating to a new CryptoKey, use rewrite/batch operations and inventory generations.
9. Operations periodically test-downloads selected older invoices to verify older key versions remain usable.

### 13.3. Why Not Choose CSEK by Default for All Invoices?

The application team needs Cloud Run pipelines, retries, background jobs, backups, PDF retrieval, and data-management integrations. With CSEK, clients must protect and supply the exact raw key for every object access, and several tools do not support CSEK. **CMEK via Cloud KMS** is usually far easier to govern when the main requirement is **key lifecycle control and audit evidence**.

If a stricter requirement demands that only external apps ever see plaintext, evaluate client-side encryption with engineered key escrow and recovery—do not equate that requirement with standard CMEK.

## 14. Troubleshooting Encryption Incidents

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| Cannot set default CMEK | Wrong KMS key location, invalid key, or missing service agent permission | Check bucket location, KMS resource, and IAM role |
| Object upload returns `403` | Missing `storage.objects.create`, bad KMS key IAM, or another blocking policy | Read error details, bucket IAM + key IAM + enforcement rules |
| Bucket has default CMEK, yet object uses CSEK | Request supplied a per-object CSEK | Inspect client flags/headers and enforcement rules |
| Old objects still use `key-A` after switching default to `key-B` | Changing bucket default **is not retroactive** | Rewrite objects/generations needing migration |
| Object download fails after rotation | Old version disabled/destroyed, or service agent lost permission | Inspect object encryption metadata and KMS key versions |
| Enabled CMEK-only, and legacy pipeline uploads fail | Pipeline sends invalid CSEK or Google-managed requests | Check encryption enforcement and update client |
| Created KMS key in `global` while bucket is in `asia-southeast1` | Key ring location mismatches bucket | Create key in the matching location |
| Cannot view KMS key policy | User has Storage role but lacks permissions on the key project | Coordinate with KMS admin; never self-grant Owner |
| KMS HSM/EKM requests fail or run slow | Quotas, external key manager availability, latency, or auth | Check quotas, KMS logs, and EKM provider status |
| Re-encryption impacts billing | Rewriting many objects, storage class/early deletion, or retention | Estimate API operations and migration schedule |
| Console cannot download CSEK object | Console does not support that CSEK flow | Use supported tools/APIs and secret-managed keys |
| Hash/checksum missing in object listings | CMEK/CSEK has metadata limits on LIST | Use object metadata GET when authorized |
| Key disabled, yet object metadata remains viewable | Names/metadata do not depend on payload CMEK | Use IAM to restrict metadata; do not treat disable as delete |
| Ransomware deleted objects despite CMEK | Encryption does not prevent IAM-authorized deletes | Use least-privilege IAM, retention/soft delete/backups |
| Dev team reads objects without KMS IAM | Cloud Storage uses its **service agent** on behalf of requests | Audit storage IAM and KMS service agent IAM separately |

### 14.1. Investigation Order Before Granting Extra Permissions

1. Record **principal**, bucket/object/generation, operation (`get/create/rewrite`), timestamp, and exact error.
2. Check **Storage IAM** at bucket/project and inherited bindings.
3. Check bucket **default CMEK** and **encryption enforcement**.
4. Inspect **per-object encryption metadata** to see whether the object uses CMEK, CSEK, or an older key.
5. If CMEK, verify the **service agent of the exact bucket project**, KMS permissions, location, primary version, and key state.
6. If CSEK, verify key custody and that the client supplies the right key in the request (never paste raw keys into logs).
7. Check Storage/KMS Cloud Audit Logs and app logs with appropriate permissions.
8. Change configurations only after identifying root cause; test with **non-sensitive** objects in a sandbox with a rollback plan.

### 14.2. Logging and Protecting Audit Logs

- **Cloud Storage Cloud Audit Logs:** configuration changes and data access per enabled log types/features.
- **Cloud KMS audit logs:** key administration and key usage per Data Access log settings.
- **Cloud Monitoring:** request errors, latency, quotas, and application signals.
- **Billing reports:** Cloud KMS/Cloud HSM/Cloud EKM, object storage, rewrites, retention, and network costs.

Never write raw encryption keys, access tokens, signed URLs, or sensitive payloads to logs. KMS audit logs may include resource names and principals; restrict log access strictly to authorized personnel.

## 15. Pricing and Key Lifecycle Operations

### 15.1. Cost Sources

| Component | Potential Charges |
|---|---|
| Cloud Storage object data | Storage charges by class, location, and duration |
| Storage API operations | Uploads/downloads/copies/rewrites, metadata requests |
| Soft delete / versioning / retention | Retained copies and noncurrent generations |
| Cloud KMS key versions | Key/version fees per product tier |
| Cloud KMS cryptographic operations | Depends on key protection level and operation type |
| Cloud HSM / Cloud EKM | Separate pricing, quotas, and operational costs |
| Data transfer | Egress and cross-region transfer per configuration |
| Cloud Logging | Log ingestion, storage, retention, and queries per service rules |
| Application integration | Failure handling, DR, compliance, and audit operational effort |

Do not assume fixed unit prices, as rates vary by location, SKU, and agreements. With Cloud KMS **software keys**, certain Cloud Storage cryptographic operations do not consume KMS quotas the same way HSM/EKM keys do; when using HSM or EKM, pay close attention to quotas, latency, and external dependencies.

### 15.2. Risk-Based Decisions

| Business Requirement | Starting Option to Evaluate |
|---|---|
| Public/static files with no self-managed key requirement | Google default encryption + appropriate IAM/public access policies |
| Invoices/contracts needing auditable key governance | CMEK, dedicated key project, and auditing |
| Organization policy mandates HSM-backed keys | CMEK with Cloud HSM where compatible |
| Policy requires key material stored outside Google Cloud | Cloud EKM or client-side encryption per threat model |
| Application must supply raw keys from an external system | CSEK if integration limits are acceptable |
| Must ensure new objects cannot use Google default or CSEK | Bucket default CMEK + CMEK-only encryption enforcement |
| Must prevent accidental deletion / guarantee data recovery | Versioning, soft delete, retention, backups; **never encryption alone** |

## 16. Practice Exercises and Self-Assessment

### Exercise 1 — Defaults Are Not Retroactive

Bucket `reports` initially uses Google default encryption. On Feb 01, an admin enables default CMEK `key-A`; on Mar 01, they switch the default to `key-B`. Two objects `jan.csv` and `feb.csv` were uploaded in January and February respectively without per-object keys in the requests.

**Questions:** Which key protects each object? What is the risk if `key-A` is destroyed right after Mar 01? What must be done to move all objects to `key-B`?

**Hint:** `jan.csv` still uses Google default encryption; `feb.csv` uses `key-A`; changing the default does not rewrite objects. Inventory old generations, rewrite objects, and test reads before retiring `key-A`.

### Exercise 2 — Per-Object Override

A bucket defaults to CMEK `key-A`. A client uploads a new object with CSEK while bucket policy still permits both CMEK and CSEK.

**Questions:** Which method does the object use? How can you force all new objects to use CMEK only?

**Hint:** A valid CSEK request overrides the bucket default; configure encryption enforcement to restrict Google default and CSEK.

### Exercise 3 — KMS Key Location

A bucket resides in a configurable dual-region with location code `ASIA` across a valid region pair. The security team proposes creating the key ring only in `asia-southeast1`.

**Questions:** Is that valid? Which key ring location should be chosen?

**Hint:** The key ring must match the **bucket's location code**; for this configurable dual-region that is `asia`, not an individual member region.

### Exercise 4 — Service Agent

A Java application has `roles/storage.objectViewer` on a bucket. The Cloud Storage service agent loses `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the CryptoKey, and the API fails to download CMEK objects.

**Questions:** Should you grant `roles/cloudkms.admin` to the application? What should the administrator inspect?

**Hint:** No. Check the bucket project's service agent, IAM on the CryptoKey, key state/version, and errors; restore the proper role on the service agent once approved.

### Exercise 5 — Rotation and Data Loss Risk

After rotation, a team sees `CryptoKeyVersion 1` is no longer primary and wants to destroy it right away "for safety." Several objects have not been rewritten.

**Questions:** Could this render objects unreadable? What inventory and tests are needed?

**Hint:** Yes. Older objects still depend on version 1; inventory every generation, rewrite, test downloads, check retention/backups, and destroy only after formal approval.

### Exercise 6 — CSEK and Integrations

A Storage Transfer Service pipeline must copy data from bucket A to B. Some source objects use CSEK.

**Questions:** What must be checked before running the transfer? Why can CSEK create more friction than CMEK?

**Hint:** Check integration limitations and plan rewriting/converting CSEK objects to CMEK or Google default in a controlled environment; raw keys must never leak into pipelines or logs.

### Exercise 7 — Designing for a Java System

A team deploys a Java API on Cloud Run storing user documents in Cloud Storage and must prove 90-day key rotation while separating key management from object administration. The business also requires recovery from accidental deletion.

**Requirement:** Design the bucket, key project, service agent IAM, encryption enforcement, rotation/rewrite, and backup/soft delete. Which alerts would detect a disabled key or lost permissions?

**Hint:** CMEK in a separate Cloud KMS key project, bucket default CMEK + CMEK-only enforcement if needed, least-privilege service agent role; rotation does not replace rewrites; backups/lifecycle/retention handle logical deletion errors.

## 17. Pre-Production Checklist for CMEK

- [ ] Identified data classification, data owner, compliance mandates, and threat model.
- [ ] Distinguished encryption at rest, TLS in transit, and client-side encryption.
- [ ] Selected Google-managed, CMEK, CSEK, or client-side encryption based on genuine needs.
- [ ] Verified **bucket location = KMS key ring location** per region/dual-region/multi-region rules.
- [ ] CryptoKey is an appropriate **symmetric encryption key** with chosen protection level/tier.
- [ ] Separated duties across key project, bucket project, security admins, and data owners.
- [ ] Confirmed the **Cloud Storage service agent of the exact bucket project** has KMS access on the CryptoKey.
- [ ] Runtime service account holds least-privilege bucket IAM, **never KMS Admin by default**.
- [ ] Verified default key **applies only to new objects** and does not rewrite existing ones.
- [ ] Accounted for per-object key overrides and **encryption enforcement** for new objects.
- [ ] Inventoried live/noncurrent/soft-deleted generations and key dependencies before rotation/destruction.
- [ ] Tested upload/download/copy/rewrite and recovery on sample objects in a sandbox.
- [ ] Prepared playbooks for disabled KMS keys, revoked IAM, or Cloud EKM outages.
- [ ] Configured complementary protections: IAM, uniform bucket-level access, public access prevention, retention/soft delete/backups.
- [ ] Enabled appropriate audit logs/monitoring, protected KMS/metadata details, and estimated costs.
- [ ] Understood that **disabling/destroying a key does not delete objects or stop storage charges**.
- [ ] Established approvers, rollback plans, and post-change verification after every update.

## 18. Official Google Cloud Documentation

Features, UIs, and limits are updated by Google Cloud over time. Before operating on live systems, consult the documentation:

- [Cloud Storage — Data encryption options](https://docs.cloud.google.com/storage/docs/encryption)
- [Customer-managed encryption keys (CMEK)](https://docs.cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Use customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Get the Cloud Storage service agent](https://docs.cloud.google.com/storage/docs/getting-service-agent)
- [Enforce or restrict encryption types on a bucket](https://docs.cloud.google.com/storage/docs/encryption/enforce-encryption-types)
- [Customer-supplied encryption keys (CSEK)](https://docs.cloud.google.com/storage/docs/encryption/customer-supplied-keys)
- [Use customer-supplied encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-supplied-keys)
- [Cloud KMS — Customer-managed encryption keys](https://docs.cloud.google.com/kms/docs/cmek)
- [Cloud Storage bucket locations](https://docs.cloud.google.com/storage/docs/locations)
- [gcloud storage buckets update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update)
- [gcloud storage objects update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/objects/update)
- [gcloud storage service-agent](https://docs.cloud.google.com/sdk/gcloud/reference/storage/service-agent)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Cloud KMS pricing](https://cloud.google.com/kms/pricing)

**Key Takeaway:** Cloud Storage **encrypts every object at rest**; Google default encryption suits most workloads, while **CMEK** gives organizations key-lifecycle control via Cloud KMS. **A bucket's default CMEK does not re-encrypt old objects** and does not by itself block **per-object overrides**; enforcing CMEK for all new objects requires **encryption enforcement**. For critical data, key management must pair with **least-privilege IAM, key availability, tested rotation, backup/restore, logging, and cost estimation**. Destroying a key that objects still depend on can permanently render data unreadable.

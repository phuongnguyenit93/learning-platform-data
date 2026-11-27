# IAM, Uniform Bucket-Level Access, and Public Access Prevention

## Learning Objectives

After this lesson, learners will be able to:

1. Explain how **Identity and Access Management (IAM)** controls permissions on **Google Cloud Storage** buckets and objects, and distinguish IAM permissions from **Access Control Lists (ACLs)**.
2. Select least-privilege IAM roles for Java applications, report readers, upload pipelines, and bucket administrators; determine the impact of roles **inherited** from projects, folders, and organizations.
3. Understand **Uniform bucket-level access (UBLA)** accurately: once enabled, ACLs are no longer used; know the ACL migration process, restrictions on disabling it again, and the **90-day** milestone.
4. Understand **Public access prevention (PAP)** at the bucket and organization policy levels: blocking public access via **allUsers/allAuthenticatedUsers**, while recognizing key exceptions such as **signed URLs** and private bucket access via supported products.
5. Design permissions with **managed folders** or IAM Conditions without accidentally granting list or read access to the entire bucket.
6. Practice using **gcloud storage** to create private buckets, inspect and modify IAM bindings, enable UBLA/PAP, verify access, and diagnose **400/401/403/412** errors.
7. Design data security across Compute Engine, GKE, Cloud Run, Cloud Storage, CI/CD, and Java applications; evaluate logging, monitoring, cost, reliability, and change processes.

## 1. Context: Multiple Consumers Needing Different Permissions in One Bucket

Suppose **An Loc** operates an e-commerce system on Google Cloud:

- A **Java API** on Cloud Run writes product images to a bucket.
- An **image-processing application** on GKE needs to read raw images and write optimized ones.
- **Analysts** need to read monthly CSV reports.
- **Customers** should only view published product images and never download contract documents.
- **CI/CD pipelines** need to upload artifacts without permissions to delete production data.

If every component receives **roles/storage.admin** on the project, a single leaked token or misconfiguration could impact multiple buckets. Conversely, if permissions are granted on an individual object via ACL and the company later enables UBLA, clients relying on ACLs can lose access immediately.

In the **CLOUD_PROVIDERS_GCP** module, learners organize projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, and databases, while securing resources, automating releases, and monitoring reliability and cost. This topic focuses on **who is allowed to do what with Cloud Storage data**, how to standardize permission management, and how to reduce the risk of accidental internet exposure.

**Three security questions to resolve:**

1. **Who has access?** User accounts, Google Groups, service accounts, or federated principals.
2. **Where does the permission apply?** Organization, folder, project, bucket, managed folder, or object depending on the mechanism in use.
3. **Are guardrails preventing public exposure?** UBLA eliminates ACLs, whereas PAP blocks public IAM/ACL grants. The two features solve **two different problems**.

## 2. Foundational Concepts: Principal, Role, Permission, Policy, and ACL

### 2.1. IAM Policy

An **IAM allow policy** consists of **bindings**: each binding attaches a **role** to one or more **principals** and may include a **condition**.

| Component | Meaning | Example |
|---|---|---|
| **Principal** | Identity being granted access | `user:analyst@example.com`, `group:data-team@example.com`, `serviceAccount:writer@project.iam.gserviceaccount.com` |
| **Permission** | Specific allowed action | `storage.objects.get`, `storage.objects.create`, `storage.objects.list` |
| **Role** | Collection of permissions | `roles/storage.objectViewer`, `roles/storage.objectCreator` |
| **Binding** | Who receives which role on a resource, optionally with a condition | The `data-team` group receives Object Viewer on the `reports` bucket |
| **Policy inheritance** | Permissions granted on an ancestor flow down to child resources | Object Viewer granted on a project applies to buckets in that project |
| **IAM Conditions** | CEL expressions restricting time or supported target resources | Only objects with prefix `reports/` or before a timestamp |

Conceptual bucket policy example (abbreviated—**not a complete policy file to overwrite with**):

~~~yaml
bindings:
  - role: roles/storage.objectViewer
    members:
      - group:analysts@example.com
  - role: roles/storage.objectCreator
    members:
      - serviceAccount:upload-worker@shop-prod-001.iam.gserviceaccount.com
~~~

In this example, the `analysts` group can view/list objects, while the worker's service account can create new objects. Exact effective permissions also depend on the **resource**, **IAM Conditions**, **IAM deny**, **organization policies**, and related constraints.

### 2.2. ACL (Access Control List)

**Fine-grained access** is the Cloud Storage mode that uses **IAM and ACLs side by side**. ACLs can grant **READER/WRITER/OWNER** under the Cloud Storage model for a bucket or object. In a bucket without UBLA enabled, **either an IAM grant or an ACL grant** can allow a request unless another blocking mechanism applies.

Example:

- Bucket IAM does not grant **Object Viewer** to an account.
- However, an individual object has an ACL granting that account **READER**.
- Unless blocked by another control, that account can read the object.

This makes auditing harder: inspecting only the bucket's IAM policy does not reveal permissions granted via object ACLs. ACLs can also include **allUsers** or **allAuthenticatedUsers**, causing unexpected public exposure.

### 2.3. Comparing the Two Systems

| Criterion | IAM | ACL |
|---|---|---|
| Primary scope | Organization/folder/project, bucket, and supported managed folders | Bucket and individual objects in fine-grained mode |
| Granularity | Rich roles/permissions, inheritance, and supported conditions | READER/WRITER/OWNER per bucket/object |
| Unified Google Cloud system | Yes | No; specific to Cloud Storage |
| Assignable to Google Groups / service accounts | Yes | Has corresponding capabilities, but a different model from IAM |
| Status when UBLA is enabled | **Primary authorization mechanism** | **Disabled** |
| Governance risk | Granting overly broad roles at higher levels | Scattered per-object permissions that are hard to audit |

**Principle:** For new buckets, prefer **UBLA + IAM** unless there is a specific ACL compatibility requirement. For existing buckets, **inventory ACL usage before switching**—never turn it on in production first and hunt down broken access afterward.

## 3. How Does IAM Inheritance Work?

### 3.1. Hierarchical Resources

~~~mermaid
flowchart TD
    O["Organization"] --> F["Folder"]
    F --> P["Project shop-prod-001"]
    P --> B["Bucket shop-private-docs"]
    B --> M["Managed folder contracts/"]
    M --> X["Objects with prefix contracts/"]
    O -. "Ancestor IAM roles can inherit" .-> X
~~~

A role granted on a **project** can apply to multiple buckets/objects. A role on a **bucket** affects only that bucket and objects/managed folders inside it per its permissions. A role on a **managed folder** applies only to objects under the corresponding prefix.

**Allow policies are additive**: if you grant analysts read access at the project level, you cannot "narrow" that access merely by omitting them from a bucket's IAM policy. You must adjust the ancestor policy, reorganize resources, or apply an appropriate control mechanism.

### 3.2. Do Not Confuse Direct Policy with Effective Access

~~~text
Project shop-prod-001:
  group:data-team → roles/storage.objectViewer

Bucket shop-private-docs:
  serviceAccount:upload-worker → roles/storage.objectCreator

Result:
  data-team can still read objects in shop-private-docs
  because the role is inherited from the project,
  even though the bucket's direct IAM policy does not list data-team.
~~~

**gcloud storage buckets get-iam-policy** mainly shows direct bindings on the bucket and does not necessarily display every inherited binding. To verify effective access, inspect IAM across project, folder, organization, IAM deny, and other policies.

### 3.3. IAM Allow, IAM Deny, and Organization Policy

**IAM deny policies** are a layer that can block permissions even when IAM allow or ACL grants access. Deny policies apply at the **organization/folder/project** level, not directly on buckets or managed folders.

The **Organization Policy Service** can also enforce guardrails such as:

- **constraints/storage.publicAccessPrevention**: enforces that buckets in scope cannot grant public access.
- **constraints/storage.uniformBucketLevelAccess**: requires new buckets to use UBLA and prevents disabling UBLA on buckets where it is already enabled, though it does not automatically flip UBLA ON for existing buckets where it is disabled.
- Other constraints on location, encryption, retention, or bucket creation per enterprise policy.

**These layers do not replace one another:** IAM determines roles/permissions; UBLA selects the authorization mechanism; PAP blocks public principals; organization policies set governance guardrails from above.

## 4. Cloud Storage IAM Roles to Remember

The following roles illustrate **common permissions** and do not replace checking the official permission lists.

| Role | Name | Core Capabilities | Notes |
|---|---|---|---|
| **Storage Object Viewer** | `roles/storage.objectViewer` | Read objects and **list objects** | Do not grant project-wide to a team that only needs one bucket |
| **Storage Object Creator** | `roles/storage.objectCreator` | Create new objects | **Cannot** read, delete, or overwrite existing objects with this role alone |
| **Storage Object User** | `roles/storage.objectUser` | Create, read, update/delete objects and related actions | Broader than Object Creator; fits workers needing modify/delete |
| **Storage Object Admin** | `roles/storage.objectAdmin` | Broad control over objects | Does not necessarily grant admin control over all bucket settings |
| **Storage Bucket Viewer** | `roles/storage.bucketViewer` | Read bucket/metadata within granted scope | Does not imply permission to download object content |
| **Storage Admin** | `roles/storage.admin` | Broad administration of buckets, objects, and IAM in scope | Powerful role; restrict principals and scope |
| **Storage Folder Admin** | `roles/storage.folderAdmin` | Administer managed folders and policies per role permissions | Do not grant casually to app uploaders |

### 4.1. Subtle Differences That Cause Errors

- **roles/storage.objectCreator** only permits creating new objects: workflows that overwrite an existing object name or delete old objects may get **403**, because Cloud Storage typically also requires **storage.objects.delete** to replace an existing object.
- **roles/storage.objectViewer** includes **storage.objects.list**. If the requirement is strictly "GET an object whose exact name is known" without listing the entire bucket, consider a **custom role** and proper resource scoping rather than broad Object Viewer.
- **roles/storage.admin** at the **project** level affects many buckets, making it far stronger than granting it on **a single bucket**.
- **Legacy roles / convenience values** exist for backward compatibility; check whether projects use basic roles **Owner/Editor/Viewer**, as principals may inherit broader bucket access through them than intended.
- Check **storage.buckets.getIamPolicy** and **storage.buckets.setIamPolicy** separately when managing IAM bindings; object read permission does not grant policy edit rights.

### 4.2. Illustrative Authorization Matrix

| Principal | Recommended Scope | Suggested Role | Do Not Grant by Default |
|---|---|---|---|
| Java service writing new images | `images-inbox` bucket or dedicated managed folder | Object Creator | Project-wide Storage Admin or Editor |
| Image optimization worker needing read & replace | Purpose-isolated bucket/managed folder | Object User or tailored custom role | Project-wide Owner |
| Analytics team reading reports | `reports/` managed folder or dedicated `reports` bucket | Object Viewer | Object Admin |
| CI pipeline uploading immutable artifacts | Dedicated pipeline artifacts bucket | Object Creator | Object Admin if delete is unneeded |
| Security team auditing bucket policies | Governed resources | Reader / appropriate audit role | Owner just to view logs |
| Storage platform admin | Specific bucket or project | Storage Admin when required | Unrestricted Admin across all projects |

## 5. What Is Uniform Bucket-Level Access (UBLA)?

### 5.1. When UBLA Is Enabled

**Uniform bucket-level access** turns off the entire **ACL** mechanism on a bucket and all objects inside it. Access is then governed **exclusively through IAM** at supported levels.

~~~mermaid
flowchart LR
    REQ["Object read request"] --> U{"UBLA?"}
    U -->|Off| BOTH["Both IAM and ACLs can grant access"]
    U -->|On| ONLY["IAM is the authorization mechanism<br/>ACLs are disabled"]
    BOTH --> O["Evaluate other guardrails"]
    ONLY --> O
    O --> PAP{"Blocked by PAP or other policies?"}
    PAP -->|Yes| DENY["Deny"]
    PAP -->|No| RESULT["Allow if valid permission exists"]
~~~

Behavior when UBLA is enabled:

- API calls to **read, create, or modify bucket ACLs or object ACLs** are no longer supported and typically return **400 Bad Request**.
- Permissions from legacy object ACLs **stop taking effect**.
- Object metadata no longer displays legacy object-ACL ownership.
- Object-level ACL operations do not apply; manage access via bucket IAM, managed folders, or supported IAM methods.

**UBLA does not block public IAM bindings.** If PAP is not enforced and an admin grants **roles/storage.objectViewer** to **allUsers** on the bucket, objects can still become public even with UBLA enabled.

### 5.2. Features That Require UBLA

Cloud Storage requires UBLA for several capabilities, including:

- **Managed folders** and IAM policies attached to managed folders.
- **IAM Conditions** attached directly to a bucket.
- **Hierarchical namespace** when using that bucket feature.
- Access for **Workload Identity Federation** and **Workforce Identity Federation** principals in Cloud Storage.

If a bucket is in fine-grained mode, adding a federated principal to an IAM/ACL policy will not work as expected; prepare a proper migration to UBLA first.

### 5.3. The 90-Day Milestone: A Potentially Irreversible Decision

**UBLA cannot be disabled once it has been continuously enabled for 90 days** on a bucket. Within a shorter window, disabling it is only allowed if all of these conditions hold:

1. UBLA has been enabled for **fewer than 90 consecutive days**.
2. The bucket has **no remaining direct IAM Conditions**.
3. The bucket **contains no managed folders**.
4. The bucket is not subject to **constraints/storage.uniformBucketLevelAccess** enforcing UBLA.

If validly disabled, Cloud Storage may **restore the ACLs saved before UBLA was enabled**; objects created while UBLA was enabled receive a default object ACL per rules. This carries a risk: **legacy ACLs might contain public grants or outdated access you no longer want**.

**Do not treat rolling back UBLA as a long-term plan.** Prepare migration and validate permissions before enabling it, rather than counting on turning it off on day 89.

### 5.4. When Should You Enable It?

**Use UBLA** for most new buckets, microservices, CI/CD, sensitive data, and environments requiring unified IAM—especially when using managed folders or IAM Conditions.

**Evaluate carefully** if legacy applications rely on object ACLs (such as uploading objects with the **publicRead** ACL or calling `ObjectAccessControls` APIs). In those cases, update the application or migrate permissions to IAM first.

## 6. What Is Public Access Prevention (PAP)?

### 6.1. What Does PAP Block?

**Public access prevention** prevents Cloud Storage buckets/objects from allowing access via public principals:

- **allUsers**: anyone, including anonymous internet clients.
- **allAuthenticatedUsers**: any valid authenticated user or service account within that identifier's scope; **it does not mean "company employees only."**

When PAP is in effect:

- Access relying on these two public principals is denied, typically with **401/403**.
- Attempts to add a public IAM binding or ACL may fail with **412 Precondition Failed**.
- **Existing public bindings** are not automatically deleted, but are **disabled while PAP is enforced**.
- If PAP is later removed without cleaning up old public bindings, those grants **can take effect again**, exposing data.

### 6.2. Two Ways to Enforce PAP

1. **Bucket level:** set **publicAccessPrevention: enforced** on the bucket.
2. **Organization/folder/project level:** use organization policy constraint **storage.publicAccessPrevention** to enforce across all buckets in scope.

Bucket metadata states:

| Value | Meaning | What to Check |
|---|---|---|
| **enforced** | The bucket itself enables PAP | PAP is active even if a higher-level policy allows public access |
| **inherited** | Follows the project/folder/org organization policy | Must inspect the **effective organization policy** to know if PAP is enforced |

**inherited does not mean public access is enabled.** It simply means the decision comes from inherited policy. A bucket with metadata **inherited** can still be protected by an organization-level policy.

### 6.3. What PAP Does **Not** Block

| Case | Blocked by This Mechanism Alone? | Explanation |
|---|---|---|
| Anonymous GET relying solely on `allUsers` | **Yes**, when PAP is enforced | Public access via `allUsers` is disabled |
| Authenticated request relying solely on `allAuthenticatedUsers` | **Yes**, when PAP is enforced | This principal is overly broad, not an internal group |
| Specific user holding IAM Object Viewer | **Not by PAP alone** | Explicitly authorized identities can still access |
| Internal Google Group holding Object Viewer | **Not by PAP alone** | Depends on IAM and other policies |
| Valid **Signed URL** generated by a principal with signing & data permissions | **No** | Signed URLs are scoped/time-limited delegation, not `allUsers` |
| Supported **private bucket access via Cloud Load Balancing / Cloud CDN** | **No** | Uses its own product-supported access mechanism |
| Object already cached publicly before PAP was enabled | **Does not immediately purge external caches** | May continue serving until TTL/cache purge takes effect |

This is crucial: **PAP does not mean nobody on the internet can download the data by any method.** Signed URLs can still be used by anyone holding the link; an authorized backend app can also serve content externally. You must govern **signers, lifetimes, delivery paths, caches, and application endpoints**.

### 6.4. Enforcement Propagation Delay

Cloud Storage lets you read back PAP state with strong consistency after an update, yet **enforcement can take up to 10 minutes**. Objects already cached externally may persist until TTL expiration or cache invalidation. During a data-exposure incident, enabling PAP is one step—**it does not replace checking caches, revoking credentials, or handling already-downloaded data**.

## 7. UBLA and PAP: Two Independent Policies—How to Combine Them?

| UBLA | PAP Enforced | Access from ACLs | Public IAM Bindings | Goal / Risk |
|---|---|---|---|---|
| **Off** | **Off / not enforced** | Can grant access | Can grant access | Legacy fine-grained mode; public risk from both ACLs and IAM |
| **On** | **Off / not enforced** | No effect | **Can still be granted** | Centralized IAM, yet **does not prevent public exposure** |
| **Off** | **On** | Non-public ACLs can still grant access | Public bindings disabled/rejected | Blocks public access while preserving legacy ACLs |
| **On** | **On** | No effect | Public bindings disabled/rejected | **Recommended baseline for private buckets**: unified IAM + public guardrail |

### 7.1. Deciding Based on Requirements

- **Internal data, contracts, backups, logs:** default to evaluating **UBLA ON + PAP enforced**.
- **Intentionally public assets:** isolate in a separate bucket with approved `allUsers` IAM where PAP is not applied, or choose **private bucket + Cloud CDN** per product features to avoid accidentally exposing an entire bucket.
- **Legacy apps using object ACLs:** plan migration first, then enable UBLA; while ACLs are temporarily required, PAP can still block public exposure.

**Check question:** "I turned on UBLA, so nobody can read the images publicly, right?" False. If IAM grants **allUsers** and PAP is not enforced, images can still be public.

## 8. Managed Folders and IAM Conditions: Finer-Grained Permissions Inside a Bucket

### 8.1. Simulated Prefixes Do Not Carry Their Own IAM Policy

A Cloud Storage object may be named **reports/2026/sales.csv**, yet **reports/** in a flat-namespace bucket is normally just a prefix. Including `/` characters in a name does not automatically create an access boundary.

A **managed folder** is a Cloud Storage resource that can carry an IAM policy for objects sharing a prefix. UBLA must be enabled before creating a managed folder.

~~~text
Bucket company-data (UBLA = ON)
├── contracts/     managed folder → Legal Team: Object Viewer
│   ├── contract-1001.pdf
│   └── contract-1002.pdf
├── reports/       managed folder → Analysts: Object Viewer
│   └── sales-2026.csv
└── images/        managed folder → Image worker: Object Creator
    └── sku-1001.jpg
~~~

**IAM on managed folders is additive with ancestor permissions**. If Analysts hold Object Viewer on the **bucket**, they can still read **contracts/** even if the `contracts/` managed folder grants them nothing. To isolate sensitive data, avoid broad bucket/project grants or separate buckets/projects.

### 8.2. IAM Conditions by Object Name

When UBLA is enabled, you can attach an **IAM Condition** on a bucket to grant access only to objects matching a prefix:

~~~text
resource.name.startsWith(
  'projects/_/buckets/company-data/objects/reports/'
)
~~~

This condition helps when users only need to read a specific subset of objects. However, **storage.objects.list** is evaluated on the **bucket resource**, so an object-name condition **cannot by itself scope bucket listing cleanly the same way it scopes object gets**. Design list permissions appropriately or use managed folders per supported capabilities, and test each API call.

**Choice:** If you want an intuitive policy for a group of objects, use **managed folder IAM**; for strong data isolation and bucket-level operations like listing/management, consider **separate buckets**.

### 8.3. Distinctions to Keep Clear

| Mechanism | Role | Notes |
|---|---|---|
| **IAM Condition on bucket** | Grants a role when resource/time conditions hold | Requires UBLA; list semantics differ from object get |
| **Managed folder IAM** | Attaches policy to objects under a prefix | Requires UBLA; bucket/project permissions still inherit |
| **Hierarchical namespace folder** | Represents a real folder in an HNS bucket | Distinct from managed folders and flat prefixes, though combinable |
| **Object ACL** | Per-object permissions in fine-grained mode | Disabled when UBLA is enabled |

### 8.4. IAM Deny Does Not Attach Directly to Managed Folders

IAM deny policies attach at the **project/folder/organization** level, not directly to buckets or managed folders; managed folders are not used as target resources in deny conditions to directly carve out child prefixes. Therefore, **permission design should start with sound bucket/project boundaries**, rather than expecting "deny one prefix" to fix an overly broad project-level allow.

## 9. Authorizing Without Long-Lived Service Account Keys

For Java applications running on Compute Engine, GKE, or Cloud Run, the runtime identity should be a **service account attached to the workload**, holding least-privilege roles on the bucket or managed folder.

~~~mermaid
flowchart LR
    APP["Java API on Cloud Run"] --> ADC["Application Default Credentials"]
    ADC --> SA["Workload service account"]
    SA --> IAM["IAM binding on bucket/managed folder"]
    IAM --> GCS["Cloud Storage objects"]
~~~

Principles:

1. **Never hardcode JSON private keys** in source code, Docker images, or YAML manifests.
2. Attach environment-specific service accounts for **dev/staging/prod**; avoid sharing broad permissions across stages.
3. For runners outside Google Cloud, use **Workload Identity Federation** where appropriate to avoid long-lived keys; **UBLA** must be enabled on the bucket for federated principals to be supported.
4. Use **Application Default Credentials** in the Google Cloud Java Client Library.
5. Never add **public IAM bindings** as a workaround for 403 errors when an app lacks permissions.
6. Distinguish **read, list, create, overwrite, and delete** permissions. Uploads using **Object Creator** can succeed on new names while failing on overwrites.

### Signed URLs Still Need Protection

A backend can generate a **V4 signed URL** allowing a customer to download an object for a limited time. PAP does not block signed URLs because they are authorized by the signer's signature and appropriate permissions.

Considerations:

- Sign only the **required object and HTTP method**.
- Use the shortest practical lifetime; avoid logging full URLs since the link acts as reusable authorization.
- Recipients can forward the link while it remains valid; a signed URL **does not verify the identity of every holder**.
- Revoking signing permissions or changing access configs does not guarantee immediate revocation of previously issued signed URLs; prepare a response plan if a link leaks.
- Estimate **egress and operation** costs when customers download heavily.

## 10. Organization Policies: Higher-Level Guardrails

### 10.1. Two Commonly Used Constraints

| Constraint | Effect | Must Understand Clearly |
|---|---|---|
| **constraints/storage.publicAccessPrevention** | Blocks public access for buckets in scope when enforced | Buckets showing metadata `inherited` may still have PAP active |
| **constraints/storage.uniformBucketLevelAccess** | Requires new buckets to use UBLA; prevents disabling UBLA once enabled | Does not automatically flip legacy non-UBLA buckets to ON |

Example:

~~~text
Organization: company.example
  └── Folder production
       └── Project shop-prod-001
            ├── Bucket private-contracts (UBLA, PAP)
            └── Bucket internal-reports   (UBLA, PAP)

Org policy on folder production:
  storage.publicAccessPrevention = enforced
  storage.uniformBucketLevelAccess = enforced
~~~

A bucket administrator **cannot disable PAP on their own** if a higher-level organization policy enforces it. Managing organization policies requires dedicated IAM roles and separate change control.

### 10.2. Policy Enforcement Can Have Latency

Changes to organization constraints can take time to propagate; Google Cloud documentation notes enforcement delays of up to **10 minutes** in some cases. Inspect effective state and test actual access. Never conclude "every object is protected" merely because the policy command returned success.

### 10.3. Scope and Exceptions

If certain assets truly must be public, do not relax PAP across the entire organization just to make one images bucket work. Design **private access via a CDN/load balancer** if suitable, or manage a narrowly scoped, reviewed/approved policy exception. For standalone projects outside an organization, you cannot rely on org policies; enable PAP directly on each bucket that needs protection.

## 11. CLI Lab A: Create a Private Bucket Following the Baseline

**Goal:** Create a bucket in a lab project with **UBLA ON + PAP enforced**, then grant read and upload permissions to the right principals. The projects, buckets, and service accounts below are **hypothetical**; replace them with resources you are authorized to use.

| Parameter | Example Value | Purpose |
|---|---|---|
| Project | **shop-dev-001** | Lab environment |
| Bucket | **shop-private-docs-REPLACE-UNIQUE** | Globally unique name |
| Location | **asia-southeast1** | Chosen for residency/latency/cost |
| Data reader | **group:analysts@example.com** | Report viewing permission |
| Upload worker | **serviceAccount:upload-worker@shop-dev-001.iam.gserviceaccount.com** | Create new objects only |

### Step 1 — Verify `gcloud` Context

~~~bash
gcloud config get-value project
gcloud auth list
gcloud projects describe shop-dev-001
~~~

Confirm you are signed in with an authorized admin account and not accidentally targeting a production project. Creating buckets requires bucket-creation permissions on the project; modifying bucket IAM requires **storage.buckets.setIamPolicy** at the appropriate scope.

### Step 2 — Create the Bucket with UBLA and PAP

~~~bash
gcloud storage buckets create \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access \
  --public-access-prevention
~~~

**This operation creates real resources and may incur charges.** Do not reuse an existing bucket name; do not treat the example project/domain names as real resources.

### Step 3 — Inspect UBLA/PAP on the Bucket

~~~bash
gcloud storage buckets describe gs://shop-private-docs-REPLACE-UNIQUE \
  --format="default(uniform_bucket_level_access)"

gcloud storage buckets describe gs://shop-private-docs-REPLACE-UNIQUE \
  --format="default(public_access_prevention)"

gcloud storage buckets get-iam-policy \
  gs://shop-private-docs-REPLACE-UNIQUE
~~~

Interpret the output alongside the **effective organization policy** and project IAM, since inherited permissions may not appear in the bucket's direct IAM output.

### Step 4 — Grant Read Access to the Analysts Group

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --member="group:analysts@example.com" \
  --role="roles/storage.objectViewer"
~~~

**Object Viewer can list all objects** in the bucket. Use this example only if the bucket is dedicated to the analysts team. If the bucket holds data for multiple teams, use managed folders or separate buckets with appropriate permissions.

### Step 5 — Grant Upload Access to the Service Account

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --member="serviceAccount:upload-worker@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"
~~~

This command does not create the service account. The service account must already exist and the workload must be permitted to use it; **storage.objects.create** will be evaluated at runtime. **Do not grant Storage Admin just to upload new objects.**

### Step 6 — Re-Read the Policy

~~~bash
gcloud storage buckets get-iam-policy \
  gs://shop-private-docs-REPLACE-UNIQUE
~~~

Verify that **the two expected bindings were added**, no unintended public principals appear, and roles are no broader than designed. If the CLI reports missing permissions, do not reflexively escalate project-wide roles; identify the specific missing permission.

### Step 7 — Test External Public Access

Suppose you uploaded a test object **healthcheck.txt** using an authorized identity. With PAP enforced, a direct anonymous request:

~~~bash
curl -I "https://storage.googleapis.com/shop-private-docs-REPLACE-UNIQUE/healthcheck.txt"
~~~

Expect the request **not to retrieve the object as public content** (typically 401/403), though exact status codes depend on endpoint, headers, caching, and object existence. **Do not rely on a single passing/failing HEAD request to prove your entire security posture**; inspect IAM/PAP and all other delivery paths.

### Step 8 — Small, Controlled Policy Change

If the analysts group no longer needs access to the bucket:

~~~bash
gcloud storage buckets remove-iam-policy-binding \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --member="group:analysts@example.com" \
  --role="roles/storage.objectViewer"
~~~

This operation **removes only the specified binding** rather than replacing the entire IAM policy like **set-iam-policy**. If a user can still read after removal, check **inherited permissions at project/folder/org**, other principals, or signed URLs instead of assuming the removal failed.

## 12. CLI Lab B: Enabling UBLA/PAP on an Existing Bucket

**Scenario:** Bucket **legacy-docs-REPLACE-UNIQUE** was created years ago with fine-grained ACLs. The goal is to switch to IAM permissions and block public access without disrupting workflows still relying on ACLs.

### 12.1. Step 1 — Inventory Before Changing

~~~bash
gcloud storage buckets describe gs://legacy-docs-REPLACE-UNIQUE \
  --format="default(uniform_bucket_level_access)"

gcloud storage buckets describe gs://legacy-docs-REPLACE-UNIQUE \
  --format="default(public_access_prevention)"

gcloud storage buckets get-iam-policy \
  gs://legacy-docs-REPLACE-UNIQUE
~~~

Also check:

- Bucket/object **ACLs and default object ACL** while UBLA is still off via Console/API or compatible tools.
- Project/folder/org IAM policies for inherited grants.
- Jobs calling **getAcl, setAcl, predefinedAcl, publicRead**, or modifying object owners.
- Service accounts, cross-project jobs, and client libraries accessing the bucket.
- Whether objects require **different per-object permissions** that cannot be mapped directly to a single bucket-wide binding.

### 12.2. Step 2 — Use Cloud Monitoring to Detect Active ACL Usage

In **Cloud Monitoring → Metrics Explorer**:

1. Select resource type **GCS Bucket**.
2. Select metric group **Authz → ACLs usage**.
3. The metric is **storage.googleapis.com/authz/acl_operations_count**.
4. Filter by the target bucket and group by **acl_operation**.
5. Look for **OBJECT_ACCESS_REQUIRED_OBJECT_ACL**, meaning a request specifically relied on an object ACL for access.

If the count is greater than 0, identify the caller and object ACLs that must be migrated to IAM. A count of 0 lowers risk, but **does not prove no dormant workflow exists**; the metric tracks ACL usage over up to roughly **24 months** and may miss very rare batch jobs.

### 12.3. Step 3 — Map ACLs to IAM

| Legacy Permission | Migration Option to Consider | Pitfall |
|---|---|---|
| Object ACL **READER** for one user | IAM Object Viewer / legacy Object Reader at appropriate scope | Granting Viewer on the whole bucket exposes **every object**, broader than the old ACL |
| Object ACL **OWNER** | IAM role with required permissions, scoped to resource | Do not default to Storage Admin |
| Default object ACL applied to new objects | Bucket/managed folder IAM bindings for uploaders and readers | Object Creator does not allow overwrites |
| Public ACL on a few images | Separate bucket for public assets or private delivery/signed URLs | UBLA has no object ACLs; PAP blocks public IAM |
| ACLs by team or prefix | **Managed folder IAM**, IAM Conditions, or multiple buckets | Requires UBLA first; inherited permissions remain active |

A 1:1 mapping is not always feasible. Sometimes the right move is **splitting data across multiple buckets** before enabling UBLA, rather than turning single-file read access into access across an entire repository.

### 12.4. Step 4 — Migrate Workflows to IAM and Test

Execute in staging or on a representative set of objects:

1. Grant least-privilege IAM bindings before removing ACLs.
2. Verify service accounts actually have the required **storage.objects.get/create/list/delete** permissions.
3. Update legacy applications so they stop reading or writing object ACLs.
4. Run positive tests for authorized readers and writers.
5. Run negative tests for unauthorized principals and out-of-scope paths.
6. Save a policy snapshot/export for change review; avoid including tokens or sensitive data in reports.

### 12.5. Step 5 — Enable UBLA

~~~bash
# Impacts access control on an existing bucket.
gcloud storage buckets update \
  gs://legacy-docs-REPLACE-UNIQUE \
  --uniform-bucket-level-access
~~~

Once enabled, requests relying solely on object ACLs are rejected. Schedule a maintenance/change window with support on standby to monitor 403/400 errors after rollout.

### 12.6. Step 6 — Enable PAP and Clean Up Public IAM Bindings

~~~bash
gcloud storage buckets update \
  gs://legacy-docs-REPLACE-UNIQUE \
  --public-access-prevention
~~~

**Do not stop at this command:** if legacy public IAM/ACLs exist, PAP only **disables** them. On a UBLA-ON bucket, audit and **remove any remaining public IAM bindings**, and document them so they cannot re-expose data if PAP is ever altered later.

Example command to remove **one** public binding if it actually exists in the bucket policy:

~~~bash
gcloud storage buckets remove-iam-policy-binding \
  gs://legacy-docs-REPLACE-UNIQUE \
  --member=allUsers \
  --role=roles/storage.objectViewer
~~~

This is only an example for removing a common role. Check all bindings and IAM Conditions, as other public roles may exist. If protected by an organization policy, **do not weaken parent policies** just to run test steps.

### 12.7. Step 7 — Verify and Rollback Considerations

~~~bash
gcloud storage buckets describe gs://legacy-docs-REPLACE-UNIQUE \
  --format="default(uniform_bucket_level_access,public_access_prevention)"

gcloud storage buckets get-iam-policy \
  gs://legacy-docs-REPLACE-UNIQUE
~~~

Verify on the **data plane** (using real application identities), not just metadata readbacks:

- Authorized identities: upload/download/list per design.
- Unauthorized identities: properly denied.
- Anonymous requests: cannot read private objects.
- Legacy clients still calling `ObjectAccessControls` must be migrated.

**UBLA rollback has strict conditions:** only within 90 consecutive days of enabling, with no remaining managed folders or bucket IAM Conditions, and no org constraint enforcing UBLA. Disabling UBLA can restore old ACLs, requiring a fresh review for public exposure. **Never disable PAP** to troubleshoot access issues without checking for lingering public bindings.

## 13. CLI Lab C: Managed Folder for a Document Group

**Scenario:** Bucket **company-docs-REPLACE-UNIQUE** has UBLA/PAP enabled. The legal team should only read objects under **contracts/** and must not read data under **payroll/**.

**Critical prerequisite:** the legal principal **must not hold Object Viewer at the project or bucket level** covering all objects. If a broad ancestor role exists, granting a role on a managed folder **will not restrict** that inherited access.

### 13.1. Create the Managed Folder

~~~bash
# Bucket must have UBLA enabled and caller needs permissions to manage managed folders
gcloud storage managed-folders create \
  gs://company-docs-REPLACE-UNIQUE/contracts/
~~~

A managed folder is a distinct resource, not just a prefix string. Its name must end with **/** and comply with Cloud Storage naming rules.

### 13.2. Grant Permissions on the Managed Folder

~~~bash
gcloud storage managed-folders add-iam-policy-binding \
  gs://company-docs-REPLACE-UNIQUE/contracts/ \
  --member="group:legal@example.com" \
  --role="roles/storage.objectViewer"
~~~

Managed folder IAM applies to objects whose names begin with **contracts/**, avoiding per-object ACLs. With nested managed folders, permissions inherit/accumulate along the supported hierarchy.

### 13.3. Inspect Policy and Verify Reality

~~~bash
gcloud storage managed-folders get-iam-policy \
  gs://company-docs-REPLACE-UNIQUE/contracts/

gcloud storage buckets get-iam-policy \
  gs://company-docs-REPLACE-UNIQUE
~~~

Run verification checks using a real legal user identity:

| Test | Expected Result |
|---|---|
| GET **contracts/contract-001.pdf** | Succeeds if object exists, IAM suffices, and other guardrails allow |
| GET **payroll/salary.csv** | Denied if no other inherited grant exists |
| DELETE **contracts/contract-001.pdf** | Denied with Object Viewer |
| Public GET on object under `contracts/` | Denied when PAP is enforced |
| List entire bucket | Must verify against actual permissions; do not assume a folder viewer can discover all prefixes |

**Use managed folders when many objects genuinely share an access group**, not as a replacement for all bucket/project segmentation. When datasets have sharply different sensitivity levels, separate buckets or projects give cleaner control over inherited permissions and retention.

## 14. IAM Conditions by Prefix and Time

In a **UBLA ON** bucket, you can attach conditions to IAM bindings when a role should apply only to matching objects.

### 14.1. Example: Read-Only Access to Report Objects

CEL condition:

~~~text
resource.name.startsWith(
  'projects/_/buckets/company-docs-REPLACE-UNIQUE/objects/reports/'
)
~~~

This can be attached to an appropriate principal's IAM binding. Illustrative IAM Condition structure for review:

~~~yaml
title: ReportsPrefixOnly
description: Apply permission only to objects under reports/
expression: "resource.name.startsWith('projects/_/buckets/company-docs-REPLACE-UNIQUE/objects/reports/')"
~~~

When using **gcloud storage buckets add-iam-policy-binding**, you can pass the condition file with **--condition-from-file**. Assuming the operator saved the structure above as **reports-condition.yaml**:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://company-docs-REPLACE-UNIQUE \
  --member="group:report-auditors@example.com" \
  --role="roles/storage.objectViewer" \
  --condition-from-file=reports-condition.yaml
~~~

**Limitation:** Because **storage.objects.list** is checked on the **bucket resource**, a condition matching only object resource names **does not allow arbitrary listing inside `reports/` the same way it allows object gets**. Design list permissions properly or use managed folders per product capabilities, and test each API.

### 14.2. Time-Based Expiration Condition

~~~text
request.time < timestamp('2027-01-01T00:00:00Z')
~~~

Useful when granting temporary access to an audit partner. However, IAM Conditions **do not delete the binding upon expiration**; the binding stays in the policy. Clean up expired bindings periodically and track IAM policy versions, especially when tools use **set-iam-policy**.

### 14.3. Do Not Use Unsupported CEL Attributes

Cloud Storage bucket IAM Conditions only support a specific set of attributes, commonly **resource.name, resource.type, and request.time**. Do not assume context properties like **device posture, client IP, or request.path** are supported in Cloud Storage IAM bindings.

To enforce network-level controls, evaluate supported products and mechanisms such as **VPC Service Controls**, bucket IP filtering, or appropriate network architectures. Never copy an IAP IAM Condition verbatim expecting Cloud Storage to interpret the same request fields.

## 15. Design Scenario: Publishing Content While Keeping Private Buckets

An e-commerce app needs customers to view public product images while keeping contracts and reports private.

### 15.1. An Easy Mistake

Putting images and contracts in the same bucket and granting:

~~~text
member: allUsers
role: roles/storage.objectViewer
scope: entire bucket
~~~

If PAP is not enforced, that binding allows **anyone to read and list all objects** in the bucket, including sensitive files. Enabling UBLA does not prevent this.

### 15.2. Separation of Concerns Design

~~~mermaid
flowchart LR
    CUSTOMER["Customers"] --> EDGE["HTTPS LB / Cloud CDN or signed URL"]
    EDGE --> IMG["Bucket product-media<br/>UBLA + controlled public delivery"]
    API["Java API on Cloud Run"] --> PRIVATE["Bucket private-contracts<br/>UBLA + PAP"]
    ANALYST["Authorized analysts"] --> REPORT["Bucket reports<br/>UBLA + PAP"]
    CI["Deploy pipeline"] --> ART["Bucket artifacts<br/>UBLA + PAP"]
~~~

| Bucket | Data | Recommended Policy | How Accessed |
|---|---|---|---|
| **product-media** | Approved product images | UBLA; PAP can remain enforced when using private bucket access/CDN or signed URLs per supported design | Served to frontend via designed delivery tier |
| **private-contracts** | Customer contracts | UBLA ON, PAP enforced | Backend service account and authorized internal staff |
| **reports** | Revenue reports | UBLA ON, PAP enforced | Analytics team via managed folder/bucket IAM |
| **artifacts** | CI/CD packages | UBLA ON, PAP enforced | Pipeline service account and authorized runners |

**Do not relax PAP across an entire project** just to expose a few images. Use **private bucket access** through a supported load balancer/CDN, or signed URLs in a controlled flow. If directly public objects are genuinely needed, isolate them in a separate bucket under an approved organizational exception.

### 15.3. When to Use Signed URLs

Signed URLs are well suited for:

- A customer downloading a private contract after the app verifies authorization.
- A partner uploading a file to a **pre-determined object path** within a short window.
- Browsers downloading large files directly without the backend proxying every byte.

Design must evaluate **expiration time, signing per GET/PUT method, HTTPS, Content-Type if signed, signer permissions, auditing, and link-sharing risk**. PAP does not disable signed URLs, so **signed URLs cannot be treated as blocked by a policy forbidding public IAM**.

## 16. Java Application and CI/CD Pipeline Examples

### 16.1. Java on Cloud Run Uploading with Application Default Credentials

Suppose the Java API should only upload new objects into a private bucket. Cloud Run's service account holds **roles/storage.objectCreator** on the appropriate bucket.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PrivateDocumentUploader {
    private final Storage storage =
        StorageOptions.getDefaultInstance().getService();

    public void uploadOnce(String bucket, String objectName, Path file)
            throws Exception {
        BlobInfo target = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("application/pdf")
            .build();

        // Intended for small objects in this lesson; production should use streaming.
        byte[] data = Files.readAllBytes(file);
        storage.create(
            target,
            data,
            Storage.BlobTargetOption.doesNotExist()
        );
    }
}
~~~

**Key security points:**

- The Java client uses **ADC**, eliminating the need to upload JSON keys to Cloud Run.
- **doesNotExist()** prevents accidentally overwriting an existing object; handle precondition-failed errors properly rather than retrying infinitely.
- **Object Creator** allows creation, not download or deletion. If the app must return content, grant an appropriate read role on the bucket/managed folder or separate the read service.
- For large files, never read the entire file into RAM as in this snippet; use **streaming/resumable uploads** supported by the client library.
- Validate **objectName** so users cannot supply paths targeting another user's prefix inside the same bucket and bypass application authorization logic.

### 16.2. CI/CD Outside Google Cloud

For example, GitHub Actions builds an image/artifact and uploads it to a release-only bucket:

1. Configure **Workload Identity Federation** between GitHub OIDC and Google Cloud, restricting trusted repos, branches, and environments.
2. Use a **dedicated deploy service account** granted least-privilege IAM on the artifacts bucket.
3. Enable **UBLA** so federated principal access works within Cloud Storage's supported scope.
4. Enable **PAP** since artifacts do not require public access.
5. Use generation preconditions or immutable version/hash-based artifact names to prevent cross-pipeline overwrites.
6. Run negative tests: unauthorized forks, repos, or branches must fail to upload or read sensitive artifacts.

**Never use `allAuthenticatedUsers`** so CI/CD "gets access without detailed auth." That identifier is not scoped to your organization and covers external authenticated accounts as well.

### 16.3. Differences Between Data Plane and Control Plane

| Operation | Permission Group to Consider | Warning |
|---|---|---|
| Upload new object | `storage.objects.create` | Object Creator does not imply read or overwrite |
| GET object | `storage.objects.get` | Also subject to IAM allow/deny and PAP if accessed via public principals |
| List objects | `storage.objects.list` | Usually checked on the bucket, unlike object-level get |
| Delete object | `storage.objects.delete` | Data-loss risk; consider soft delete/versioning |
| View bucket metadata | `storage.buckets.get` | Does not imply permission to read object contents |
| Edit bucket IAM | `storage.buckets.setIamPolicy` | Higher privilege than object read/write |
| Change UBLA/PAP | `storage.buckets.update` and related permissions | Impacts many clients; requires review and proper authority |

## 17. Audit Logs, Monitoring, and Detecting Risky Configurations

### 17.1. Signal Categories

| Source | Purpose | Notes |
|---|---|---|
| **Cloud Audit Logs Admin Activity** | Track administrative changes like IAM/policy edits | Verify project and caller identity |
| **Data Access audit logs** | Track object access when enabled and within supported scope | May require explicit opt-in; carries logging quota/cost |
| **Cloud Monitoring ACL usage metric** | Detect ACL reliance before enabling UBLA | Metric **authz/acl_operations_count** is not a full historical list of every identity |
| **Security Command Center findings** when configured | Detect public buckets or security misconfigurations | Depends on tier, coverage, and enabled detectors |
| **IAM Policy Analyzer/Troubleshooter** per permissions and supported services | Investigate which policy grants a principal access | Must account for inherited permissions and deny |
| **Cloud Billing reports** | Monitor storage, operations, and egress costs | Audit/logging costs can scale with usage |

### 17.2. Recommended Alert Set

- Changes to **public access prevention** or **uniform bucket-level access** on production buckets.
- New IAM bindings referencing **allUsers** or **allAuthenticatedUsers**; even with PAP active, this remains risky if PAP is ever removed later.
- Repeated **setIamPolicy** attempts by non-admin accounts.
- Sudden spikes in 403/401 responses on object GET/PUT after a change.
- Unusual increases in Data Access logs or network egress on sensitive buckets.
- Unexpected issuance patterns for access keys, service accounts, or signed URLs.

### 17.3. Audit Logging Is Not an Absolute Evidence Vault

According to documentation, **access to public objects** is not logged by Cloud Audit Logs in the same detail as explicitly authorized access. Once PAP is enabled, previously public requests may shift to authenticated/logged requests, increasing Data Access log volume. This impacts **audit workflows and cost**, not just security posture.

Never log access tokens, full signed URLs, or sensitive document contents in application logs. During investigations, correlate logs across the app, load balancer/CDN, Cloud Storage, and IAM changes.

## 18. Troubleshooting: Reading Status Codes and Permission Boundaries

| Symptom | Common Cause | What to Check |
|---|---|---|
| **403 Forbidden** on Java GET object | Service account lacks **storage.objects.get**, IAM deny, or another blocking policy | ADC identity, bucket/project inherited IAM, deny, resource name |
| **403** when pipeline overwrites object | Only has **Object Creator**, missing delete or precondition failed | Create/delete permissions, generation conditions, object existence |
| **400 Bad Request** on set/get Object ACL | Bucket has **UBLA ON** | Stop calling ACL APIs; migrate to IAM |
| **412 Precondition Failed** when granting **allUsers** | PAP enforced at bucket or organization level | Bucket PAP state, org policy; never relax public guardrails to bypass |
| Bucket IAM shows no read grant, yet user still GETs | Role from project/folder/org, or client uses a signed URL | Effective IAM, group membership, signed links, and caches |
| Enabling UBLA broke legacy clients | Clients relied on object ACLs or set ACLs on upload | ACL usage metric, IAM mapping, update SDK/API calls |
| Bucket metadata shows **PAP inherited** | Org policy may or may not be enforced | Inspect effective org policy rather than guessing from the word `inherited` |
| PAP enabled, yet CDN/browser still shows old content | Object remains in external caches | Cache-Control/TTL, CDN invalidation workflow |
| PAP enabled, yet signed URL still downloads | **Working as designed** | Check signed URL issuer, TTL, and scope |
| Managed folder role granted, yet legal still reads payroll | Broad Object Viewer exists at project/bucket or via another group | Inspect inherited IAM, not only managed-folder policy |
| Prefix IAM Condition cannot list bucket | **storage.objects.list** evaluates against the bucket resource name | Design managed folder/list permissions or split buckets |
| Cannot disable UBLA | Past 90 days, has managed folders/conditions, or org policy enforces it | Verify all four rollback conditions |
| Cannot create managed folder | UBLA OFF or missing role/permissions | Bucket UBLA state, `roles/storage.folderAdmin`, and path |
| Anonymous request returns 404 instead of 403 | Object missing, endpoint/caching, or masked response | Verify policy and test against a confirmed existing object |
| Signed URL returns 403 | Expired link, bad signature, signer lacks permission, or missing object | Signer, method, timestamp, object path, headers |
| Bucket update fails with permission error despite object read access | Missing **storage.buckets.update/setIamPolicy** | Distinguish data plane from control plane |

### 18.1. Error Isolation Workflow

1. **Who is the caller?** User, service account, workload identity, anonymous, or signed URL?
2. **What is the operation?** GET, LIST, CREATE, overwrite, DELETE, ACL, or bucket IAM update?
3. **What is the resource?** Exact bucket, managed folder, object path, and generation if applicable?
4. **What is the UBLA/PAP state?** Inspect bucket metadata and effective organization policy.
5. **Which IAM grants access?** Direct bucket IAM, managed folder IAM, inherited project/folder/org, or conditional binding?
6. **Is another control blocking it?** IAM deny, VPC Service Controls, retention hold, bucket IP filtering, encryption key policy?
7. **What do negative tests show?** An unauthorized identity must actually be denied; do not test only the happy path.
8. **What changed recently?** IAM propagation, PAP enforcement, caches, bucket policy, CI/CD rollout, or client library upgrades.

Never "fix" an access error by granting **roles/editor/owner** project-wide or disabling **PAP** before finding the root cause.

## 19. End-to-End Scenario: Securing E-Commerce Data

**Hai Phong** operates three projects:

- **shop-dev-001:** test environment.
- **shop-prod-001:** Java API, Cloud Run, GKE, and production buckets.
- **security-ops-001:** monitoring system and IAM change-review workflows.

Four data groups must be managed:

1. **Product images**: customers need to view them.
2. **Invoices and contracts**: contain personal data; only backend services and authorized staff may access them.
3. **Reports**: analytics team accesses within scoped permissions.
4. **CI artifacts**: pipeline may upload; runtime downloads only when genuinely needed.

### 19.1. Proposed Bucket Structure

| Bucket | UBLA | PAP | Authorized Principals | Rationale |
|---|---|---|---|---|
| `shop-product-media` | ON | Enforced if using private delivery/signed URLs appropriately | Media publisher; designed distribution path | Avoid accidentally exposing the whole bucket to the internet |
| `shop-private-invoices` | ON | Enforced | Invoice API service account, scoped audit team | Sensitive data, strict permissions |
| `shop-internal-reports` | ON | Enforced | Analytics team or managed folder IAM | Easy to audit, prevents cross-team leaks |
| `shop-build-artifacts` | ON | Enforced | CI uploader and deployment runtime | Artifacts are supply-chain inputs |

**Project-level IAM:** avoid granting broad Storage Object Viewer/Storage Admin at the production project level, as it defeats domain-based bucket separation.

### 19.2. A Policy Violation Scenario

An engineer notices browsers failing to load images and tries adding **allUsers:roles/storage.objectViewer** to **shop-product-media**, where PAP is enforced.

Outcome:

- The command may be rejected with **412**.
- Do not disable PAP just to make the command succeed. Identify the **chosen image delivery path**: signed URLs, private bucket access/CDN per supported configuration, or a dedicated public bucket under an approved exception.
- Attempting to grant `allUsers` on a bucket holding invoices creates severe exposure risk; separating public assets into their own bucket is a necessary organizational safeguard.

### 19.3. A Disruptive Migration Scenario

A legacy `reports` bucket has one file **sensitive/monthly.csv** whose ACL granted READER only to accounting. An operator enables UBLA and grants **roles/storage.objectViewer** at the **project** level to "restore access quickly."

Consequence:

- ACL-only clients regain access, but the project-level role lets them see other buckets too.
- This is **unintended privilege escalation**. Revoke the overly broad role and grant properly scoped permissions via managed folders or separate buckets.
- Before altering production policies, audit active consumers, follow rollback procedures, and log every change.

### 19.4. Acceptance Test Matrix

| Test | Expected Result |
|---|---|
| Cloud Run invoice service GETs an authorized invoice | Succeeds |
| A dev service account GETs a production invoice | Denied |
| Customer without a signed URL GETs an invoice directly | Denied |
| Customer with a properly scoped/valid signed URL downloads one file | Succeeds if signer/authorization are valid |
| CI uploader creates a new artifact version | Succeeds |
| CI uploader with Object Creator overwrites an old artifact | Fails under least-privilege role |
| Anonymous GET on contracts/reports buckets | Denied when PAP is enforced |
| Engineer attempts to add `allUsers` on a protected bucket | Blocked by PAP |
| Analysts team reads reports but cannot read invoices | True if no broad inherited role exists |
| Disable UBLA after 90 consecutive days | Not permitted |
| Audit/logs | Evidence of policy changes and data access within enabled logging scope |

### 19.5. Post-Release Operations

- Periodically review **project/bucket/managed-folder IAM bindings**, unused groups, and stale service accounts.
- Monitor **public access posture**, PAP/UBLA changes, and IAM violations.
- Track **egress/download volume**, since even a private bucket heavily downloaded via signed URLs or backends can incur substantial charges.
- Run drills for **revoking access if tokens or signing capabilities leak** and handling cached/distributed content.
- Maintain appropriate backups, soft delete, versioning, and retention; IAM/PAP do not recover data after deletion or corruption.

## 20. Practice Exercises and Suggested Answers

### Exercise A — Distinguishing UBLA and PAP

Given a bucket **assets** with:

- UBLA = **ON**.
- PAP = **inherited**, and the organization policy does not enforce PAP.
- IAM binding **allUsers → roles/storage.objectViewer** on the bucket.

**Question:** Can objects be read publicly? Does enabling UBLA block this `allUsers` grant?

**Answer:** They can be public unless another blocking control exists. UBLA only disables ACLs; the `allUsers` IAM binding remains effective when PAP is not enforced.

### Exercise B — Upload Permissions

Service account **uploader** holds only **roles/storage.objectCreator** on a private bucket.

| Operation | Expected Result from This Role Alone |
|---|---|
| Create an object with a non-existent name | **Allowed** |
| GET the object just uploaded | **Not permitted by this role** |
| List the entire bucket | **Not permitted by this role** |
| Overwrite an existing object | **Lacks required permission to replace** |
| Delete an object | **Not permitted by this role** |

In real systems, also check roles inherited from other IAM policies. If a use case requires overwriting, grant exact required permissions after review or use new/versioned object names.

### Exercise C — Migrating ACLs to UBLA

A bucket stores 50,000 objects, including:

- Some objects with per-object ACLs granted to accounting.
- An upload job using the predefined ACL **publicRead**.
- Bucket IAM currently listing only administrators.

Plan the migration before enabling UBLA.

**Suggested Answer:**

1. Inventory default/object ACLs and check the **ACL usage metric**.
2. Identify objects requiring distinct access, splitting buckets or preparing managed folders/prefixes.
3. Refactor the **publicRead** job to use an appropriate delivery pattern; do not assume `publicRead` works under UBLA.
4. Grant least-privilege IAM roles and run positive and negative tests.
5. Enable UBLA, read back state, and monitor 400/403 errors.
6. Enable PAP for private data and remove lingering public IAM bindings.
7. Document the <90-day rollback window and relevant organization policies.

### Exercise D — Handling a 412 Error

A pipeline tries to create an **allUsers Object Viewer** IAM binding on a bucket with PAP enabled and receives **412 Precondition Failed**.

**Question:** Does this mean the service account lacks IAM permissions? How should it be resolved?

**Answer:** Not necessarily. This is typically PAP rejecting a public binding. Clarify content distribution requirements: use signed URLs / private bucket delivery where appropriate or pursue an exception through security governance; never grant Owner/Editor or disable PAP casually.

### Exercise E — Managed Folders and Inherited Permissions

In project **finance-prod**, group **all-staff** holds Object Viewer at the project level. Bucket **finance-data** has managed folder **payroll/**, where you grant that role only to **payroll-team**.

**Question:** Can `all-staff` still read `payroll`?

**Answer:** Likely yes, because the project-level Object Viewer role flows down to buckets/objects. Managed folder IAM **does not subtract** inherited permissions. Fix the ancestor grant or separate data and policies along proper boundaries.

### Exercise F — Signed URLs Under PAP

A contract is stored in a UBLA + PAP bucket. The backend issues a 10-minute signed URL to a customer.

**Question:** Will PAP block the link? Can the customer forward the link to someone else?

**Answer:** PAP does not block signed URLs by design. Anyone holding a valid URL can use it within its signed method, object, and expiration window; treat signed URLs like bearer credentials, keep TTLs short, issue them only after app authentication, and manage leak risks.

### Exercise G — Weekend Troubleshooting

After a security change, a Java API fails to download invoices with 403s in the logs. In the Console bucket IAM view, the API's service account is not listed, though operations says the API was granted permissions at the project level.

**What to check:**

1. Which service account is actually being used via ADC?
2. Is the project-level role still active, or is there an IAM Condition or deny policy?
3. Does the bucket have managed folder IAM configured?
4. Are VPC Service Controls, retention, or CMEK affecting access?
5. Is access via direct API or signed URL?
6. Did a job or config change recently enable UBLA or PAP and alter behavior?

**Guided Answer:** 403s can stem from multiple layers. Verify caller, permission, resource, inherited roles, and guardrails; never "fix" it by making the bucket public.

## 21. Summary and Reference Documentation

**Eight Principles to Remember:**

1. **IAM** defines which actions a principal may perform; permissions can be **inherited** from projects/folders/organizations and combine additively with bucket/managed-folder grants.
2. **Fine-grained ACL mode** runs IAM and ACLs together, easily hiding per-object grants. **UBLA** disables ACLs and standardizes authorization on IAM.
3. **UBLA cannot be disabled after 90 consecutive days**. Before migrating, inventory ACL usage, convert to equivalent IAM, and test workflows.
4. **UBLA does not prevent public IAM**; blocking `allUsers`/`allAuthenticatedUsers` requires **PAP** or equivalent properly designed guardrails.
5. **PAP is either enforced on the bucket or inherited from org policy**; when enforced, public IAM/ACLs are blocked/disabled, though old bindings are not automatically deleted.
6. **Signed URLs and private bucket delivery can work with PAP enabled**. PAP does not replace delivery governance, signed URL TTLs, IAM, networking, or application-level authorization.
7. **Managed folders / IAM Conditions** scope permissions to groups of objects, yet remain subject to inherited IAM; **storage.objects.list** has bucket-level semantics requiring separate testing.
8. **Reliable security requires policy + testing + auditing + operations:** least-privilege permissions, separation of sensitive data, configuration monitoring, and tested rollback/recovery plans.

**Official Google Cloud Documentation:**

1. [Overview of Cloud Storage access control](https://docs.cloud.google.com/storage/docs/access-control) — choosing uniform vs. fine-grained access.
2. [Identity and Access Management for Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/iam) — policies, hierarchy, conditions, and caveats.
3. [Cloud Storage IAM roles](https://docs.cloud.google.com/storage/docs/access-control/iam-roles) — exact permissions per role.
4. [Uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access) — behavior, 90-day limit, managed folders, and migration.
5. [Use uniform bucket-level access](https://docs.cloud.google.com/storage/docs/using-uniform-bucket-level-access) — enable, disable, verify, and ACL usage metric.
6. [Public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention) — enforced/inherited states, signed URLs, and exceptions.
7. [Use public access prevention](https://docs.cloud.google.com/storage/docs/using-public-access-prevention) — Console/gcloud and org policies.
8. [Organization policy constraints for Cloud Storage](https://docs.cloud.google.com/storage/docs/org-policy-constraints) — `storage.publicAccessPrevention` and `storage.uniformBucketLevelAccess`.
9. [Manage IAM policies on buckets](https://docs.cloud.google.com/storage/docs/access-control/using-iam-permissions) — CLI roles and conditions.
10. [Managed folders](https://docs.cloud.google.com/storage/docs/managed-folders) — access control for object groups.
11. [Manage IAM for managed folders](https://docs.cloud.google.com/storage/docs/access-control/using-iam-for-managed-folders) — gcloud usage and inheritance notes.
12. [IAM permissions for Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions) — get/list/create/delete/setIamPolicy permissions.
13. [Cloud Storage troubleshooting](https://docs.cloud.google.com/storage/docs/troubleshooting) — permission, policy, and public access errors.

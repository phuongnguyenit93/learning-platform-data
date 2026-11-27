# Hands-on creating a learning project and cleaning up resources

> **Chapter:** Resource Hierarchy and Locations  
> **Module:** CLOUD_PROVIDERS_GCP  
> **Module scope:** Explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, secure resources, automate releases, and monitor reliability alongside costs.

**A project is the fundamental management boundary of a Google Cloud lab.** Each project has its own identifier, access permissions, API configurations, quotas, and billing link. If you create experimental resources without managing the project lifecycle, you can leave behind buckets, VMs, or services that keep incurring charges.

This lab walks through creating **a dedicated learning project**, determining resource location, checking IAM and billing, creating a Cloud Storage bucket with a sample file, and then **deleting the file, deleting the bucket, and verifying the result**. At the end, there is an option to shut down the entire project if it was created solely for practice.

## 1. Objectives and expected outcomes

After this lesson, you will be able to:

1. Create a project via the Google Cloud Console or Google Cloud CLI (`gcloud`), and distinguish **project name**, **project ID**, and **project number**.
2. Understand where a project sits in the **organization → folder → project** system; identify the roles of **region** and **zone** when creating resources.
3. Check IAM permissions and billing prerequisites before starting hands-on work.
4. Create a Cloud Storage bucket in a specified location, then upload and read back a file to prove the resource works.
5. Clean up resources in a safe order, check for remaining resources, and decide when to delete the entire project.

**End-of-session deliverable:** a table recording the project ID, bucket location, permission/billing check results, evidence of the uploaded file, and evidence that the bucket or project has been cleaned up.

## 2. Preparation before creating a project

### 2.1. Account and permissions

You need:

- An account permitted to access the **Google Cloud Console** at https://console.cloud.google.com/.
- Permission to create projects in your organization or learning account. In an enterprise organization, creating a project may require appropriate permissions (such as those granted via the **Project Creator** role) and may be subject to folder/organization constraints.
- If creating resources that use billable services, the project must be linked to an active **Cloud Billing account**; the user must hold corresponding linking permissions. Being able to sign into the Console **does not mean** having permission to create projects or manage billing.
- Appropriate Cloud Storage permissions to create buckets, read/write objects, and delete them. If your organization restricts these actions, practice in a sandbox project provided by an administrator.

You can practice in a **new personal project** or an **assigned lab project**. Never delete shared projects, projects holding critical data, production projects, or projects containing other people's resources.

### 2.2. Choosing a tool

There are two equivalent ways to complete this lab:

| Method | Best suited when | Key reminders |
|---|---|---|
| **Google Cloud Console** | New to GCP and want to inspect projects, hierarchy, billing, and resources visually | Always check the **Project selector** before creating/deleting |
| **Cloud Shell / gcloud CLI** | Want repeatable saved commands and exact project ID references | Run only after checking variables and active identity; prefer passing `--project` explicitly |

The `bash` blocks in this lesson use **Cloud Shell (Bash)**. Cloud Shell generally comes with `gcloud` and appropriate authentication ready. If using a local terminal, install Google Cloud CLI and sign in according to your organization's workflow before running commands. You do not need to run both methods to create two projects.

### 2.3. Safety rules for cost and cleanup

1. Use a dedicated project for the lab so you know exactly which resources need cleanup.
2. **Never assume any service is completely free.** Charges can relate to storage, request counts, network egress, and other resources; free-tier/trial credits depend on the account.
3. Before creating resources, check **Billing → Budgets & alerts** and set up an alert for your learning budget if authorized. **A budget alert is not a hard spend cap** and does not automatically shut off all services.
4. Create only the bucket and one small text file per this guide; do not create VMs, GKE clusters, Cloud SQL, or Cloud Run to finish this lesson.
5. Clean up immediately after verifying the outcome; afterward, check the billing dashboard and resource list again.

## 3. Understanding organizational structure and resource locations first

A project is not a storage location in the geographic sense. One project can own resources placed in multiple different locations, depending on the service type and organization policies.

```text
Organization (if the account belongs to an organization)
└── Folder (if the organization uses sub-groupings)
    └── Project: gcp-lab-unique-1234
        ├── IAM / enabled APIs / quotas / billing association
        ├── Cloud Storage bucket (location: asia-southeast1)
        ├── Cloud Run service (region, if deployed later)
        ├── Compute Engine VM (zone, if deployed later)
        └── Cloud SQL instance (region, if deployed later)
```

| Concept | Nature | Example / notes |
|---|---|---|
| **Organization** | Top-level governance tier when the account belongs to an organization | Policies and permissions can inherit downward |
| **Folder** | Groups projects by team, environment, or policy | May not exist in personal accounts |
| **Project** | Boundary for resource ownership, API enablement, IAM/quotas/billing | `gcp-lab-unique-1234` is only an example; you must choose an unused ID |
| **Region** | Geographic area for placing services or data depending on resource type | `asia-southeast1` is an example region in Singapore |
| **Zone** | Deployment partition within a region | `asia-southeast1-a` is an example zone, suited for resources like VMs |
| **Global resource** | Resource with global scope or governed outside standard region/zone concepts | A VPC network has global scope; VPC subnets are regional |

**Project ID** is the identifier used in CLI/APIs and is globally unique across Google Cloud. **Project number** is a numeric code assigned by Google and differs from the project ID. **Project name** is a display name and can match another project's name. You will use **project ID** throughout the examples to avoid targeting the wrong project.

With Cloud Storage, a bucket is given a **location** at creation time, which can be a region, dual-region, or multi-region among supported options. This lab picks **region `asia-southeast1`** for easy verification. This location is an example only; in real systems you must evaluate latency, data residency, service availability, recovery requirements, and cost. After creating a bucket, do not assume changing its location is as simple as renaming it.

## 4. Step 1 — Create a learning project

### Method A: via Console

1. Sign in to https://console.cloud.google.com/ and open the **Project selector** in the top bar.
2. Click **New Project**. This option may not appear if your account lacks project-creation permissions.
3. Enter a recognizable **Project name**, such as `GCP Learning Lab`.
4. Check the suggested **Project ID** or set a valid, unique ID such as `gcp-lab-unique-1234`. Do not reuse the literal example if that ID is already taken.
5. If prompted by the UI, choose the **Organization** and **Location** (organization/folder) for the project. On the project creation screen, **this Location is the placement in the resource governance hierarchy**, not the region where applications run.
6. Click **Create** and wait for the project to appear; open the newly created project and record its project ID and project number.

If you encounter a denial due to policy, quota, or permissions, use an assigned lab project or ask an administrator to grant the right permissions. Do not move projects to another organization or alter policies yourself to bypass restrictions.

### Method B: via Cloud Shell

Change the sample ID to **your own unique** ID before running:

```bash
# Set values for the lab; do not use the literal sample ID if it is already taken
PROJECT_ID="gcp-lab-unique-1234"
PROJECT_NAME="GCP Learning Lab"

# Check the active gcloud account
gcloud auth list --filter="status:ACTIVE"

# Create the project; inside an organization you may need --folder=FOLDER_ID
# or --organization=ORGANIZATION_ID depending on policy
gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME"

# Verify the newly created project
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,projectNumber,name,lifecycleState)"
```

If a parent in an organization is required, pass only the **folder or organization matching your granted permissions**, following governance guidelines. In the steps below, every resource creation/inspection command specifies the project ID explicitly to reduce the risk of running against the wrong default project.

### Checkpoint 1

Record:

| Item | Fill in your value |
|---|---|
| Project name | `________________________` |
| Project ID | `________________________` |
| Project number | `________________________` |
| Parent organization/folder (if any) | `________________________` |
| Active operator account | `________________________` |

Continue only when the selected project is **a learning project that you are authorized to modify and clean up**.

## 5. Step 2 — Check IAM, billing, APIs, and budget

### 5.1. Check permissions

In the Console, select the right project → **IAM & Admin → IAM**. Confirm your account has sufficient permissions for the assigned tasks; review other principals holding permissions if policy permits. Do not grant **Owner** or broad administrative roles to everyone just to get a lab working.

Cloud Shell can inspect the IAM policy at the **project level**:

```bash
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="table(bindings.role,bindings.members)"
```

Project IAM can be affected by inherited permissions from the organization/folder or other policies. Therefore, a project-level IAM listing does not reflect all effective permissions.

### 5.2. Check billing linkage

In the Console, open **Billing** and check whether the project is linked to an appropriate Cloud Billing account. If not and the service requires billing, link it through the Console using an authorized account per your organization's rules. Never use someone else's billing account without permission.

To view current billing linkage information (if authorized):

```bash
gcloud billing projects describe "$PROJECT_ID"
```

In the Console, create **Budget & alerts** scoped to the project if authorized. You can configure notifications when reaching projected or actual spend percentages as needed. Even with a budget in place, you must still check Billing and clean up unneeded resources.

### 5.3. Check and enable required APIs

In the Console: **APIs & Services → Enabled APIs & services**. This lab uses Cloud Storage; some environments already have the relevant API enabled. If needed, you can run:

```bash
# View enabled APIs
gcloud services list --enabled --project="$PROJECT_ID"

# Enable the API for Cloud Storage when needed
gcloud services enable storage.googleapis.com --project="$PROJECT_ID"
```

Enabling an API is a project-level setting; **it does not create data or buckets by itself**. However, subsequently creating/using resources via the API can incur charges.

### Checkpoint 2

Before creating the bucket, verify for yourself:

- The Project ID is correct, the project is authorized for practice, and it holds no production resources.
- Billing has been verified according to your account and learning environment requirements.
- Your account has sufficient permissions to create/read/delete buckets and objects.
- Budget has been reviewed and you know the end-of-lab cleanup steps.

## 6. Step 3 — Create a bucket in a specific location

Cloud Storage is an **object** storage service. A bucket belongs to a project, has a **globally unique** name, and is configured with a location, storage class, and access policies. This lab does not require a public bucket.

### Method A: Console

1. Open **Cloud Storage → Buckets** in the right project.
2. Click **Create**.
3. Enter a **globally unique** bucket name, for example `gcp-lab-unique-1234-demo-data`. The name cannot be used if another bucket already owns it.
4. Under data storage location, select location type **Region**, then pick a supported region such as **`asia-southeast1`**.
5. Choose **Standard** if prompted for a storage class for this small-file example; do not enable higher-cost options without reason.
6. Prefer **Uniform bucket-level access** and configure public access prevention per active policy. Do not grant public access for this lab.
7. Review soft delete / versioning / retention policies if displayed, since retention mechanisms can affect deletion timing and storage charges.
8. Click **Create**, then open the bucket to confirm its name and location.

### Method B: Cloud Shell

Continue using the `PROJECT_ID` set earlier. Change the bucket name if it collides:

```bash
BUCKET_NAME="$PROJECT_ID-demo-data"
BUCKET_URI="gs://$BUCKET_NAME"
BUCKET_LOCATION="asia-southeast1"

# Create a single-region bucket with uniform IAM access
gcloud storage buckets create "$BUCKET_URI" \
  --project="$PROJECT_ID" \
  --location="$BUCKET_LOCATION" \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access

# Inspect attributes of the newly created bucket
gcloud storage buckets describe "$BUCKET_URI"
```

The bucket description should show the exact **owning project** and selected **location**. Public access prevention, soft delete, versioning, and retention settings also depend on organization policies and effective defaults; review them in the Console before uploading sensitive data.

**Common errors:** bucket name already taken; missing `storage.buckets.create` permission; inactive billing; location blocked by Organization Policy; or organization configuration disallowing the requested security setting. Do not switch to a shared project to work around errors.

### Checkpoint 3

| Bucket attribute | Expected result |
|---|---|
| Name | New, unique name belonging to the learning project |
| Location | Chosen region; e.g., `asia-southeast1` |
| Storage class | Appropriate for the lab; e.g., `STANDARD` |
| Access | Data not accidentally made public |
| Objects | None yet, prior to the upload step |

## 7. Step 4 — Upload a sample file and verify

### Method A: Console

1. Inside the newly created bucket, click **Upload files**.
2. Create a local text file named `lab-note.txt` with sample content: `Hello from GCP learning lab`.
3. Upload the file to the bucket.
4. Open the object list and confirm that object `lab-note.txt` appears. You can open its details to check size and creation timestamp.

### Method B: Cloud Shell

```bash
# Create a small text file in the current Cloud Shell directory
printf 'Hello from GCP learning lab\n' > lab-note.txt

# Upload the file to the bucket
gcloud storage cp lab-note.txt "$BUCKET_URI/lab-note.txt"

# Verify the object exists in the bucket
gcloud storage ls "$BUCKET_URI"

# Read the data back from Cloud Storage to stdout
gcloud storage cat "$BUCKET_URI/lab-note.txt"
```

If the read command returns the exact uploaded text string, you have practiced the flow **create project → use a service inside the project → assign location to a resource → store and retrieve data**. You can inspect additional object details via the Console.

**Shared responsibility connection:** Google Cloud manages the storage platform, while you are responsible for choosing bucket/object permissions, classifying data, selecting locations, configuring retention, and deleting test data.

## 8. Step 5 — Inventory before cleanup

Before deleting, clearly identify resources **created by this lab**. Never run bulk deletion commands on an unverified project.

```bash
# Confirm the project is still active
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"

# List buckets belonging to the project (if authorized)
gcloud storage ls --project="$PROJECT_ID"

# List contents of the lab bucket specifically
gcloud storage ls "$BUCKET_URI"
```

If you created extra services outside this guide, check and clean up **each type** before finishing: VMs/disks and static IPs; GKE clusters; Cloud Run; Cloud SQL and backups; load balancers; Pub/Sub; Artifact Registry; object storage; and other billable resources. Do not treat `gcloud storage ls` as a full-project resource inventory tool.

One project can own resources across many **regions** and **zones**. Never check only the region used for your bucket and assume the project has no other resources.

## 9. Step 6 — Delete the object and bucket

### Method A: Console

1. Open the right project → **Cloud Storage → Buckets**.
2. Open the lab bucket and select the `lab-note.txt` file.
3. Confirm the object name and click **Delete**.
4. Verify the bucket has no remaining live objects.
5. Return to the bucket list, select **the exact lab bucket**, click **Delete**, and confirm per the prompt.
6. Refresh the bucket list; the deleted bucket name no longer appears among active buckets.

### Method B: Cloud Shell

**Double-check variables right before deleting.** Deletion is real, so the commands below are strictly for the bucket created specifically for this lab:

```bash
printf 'Project: %s\nBucket: %s\n' "$PROJECT_ID" "$BUCKET_URI"
gcloud storage ls "$BUCKET_URI"

# Delete the sample object
gcloud storage rm "$BUCKET_URI/lab-note.txt"

# Only after no needed objects remain, delete the bucket
gcloud storage buckets delete "$BUCKET_URI"

# Verify the lab bucket is gone from the current bucket list
gcloud storage ls --project="$PROJECT_ID"
```

If the bucket fails to delete, check whether there are other objects, **object versions**, **retention/hold** policies, missing delete permissions, or organization constraints. Never weaken protection policies yourself or delete other people's data just to finish the lab. Depending on soft delete or retention settings, some data may remain within a recovery window and may affect billing.

The `gcloud storage ls --project` command only verifies visible buckets; it does not prove that all resource types or all charges are zero.

## 10. Step 7 — Keep the project or delete the project?

There are **two valid ending outcomes**; choose based on how the project will be used.

| Case | Action | How to verify |
|---|---|---|
| **Learning project will be reused** | Keep the project; ensure lab buckets/objects and billable services are cleaned up | Check remaining resources, APIs, Billing, and budget alerts |
| **Project created solely for this lesson** | Verify no other user's resources exist, then **shut down/delete the project** if authorized | Project transitions to pending deletion; monitor lifecycle and Billing |

### Deleting a lab project via Console

1. Go to **IAM & Admin → Settings** or the corresponding project management page.
2. Re-verify **project name, project ID, and project number**. Confirm this is an isolated project dedicated to the lab.
3. Click **Shut down / Delete project** and read the information about affected resources.
4. Confirm with the project ID when prompted.
5. Verify the project enters pending-deletion state and is no longer an active project.

### Deleting via Cloud Shell (only for an isolated project)

```bash
# Inspect the project ID and number carefully before deleting
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,projectNumber,name,lifecycleState)"

# Run only after verifying this project was created solely for this lab
gcloud projects delete "$PROJECT_ID"
```

**Distinguishing resource deletion from project deletion:** deleting a bucket removes only the selected bucket; deleting a project puts the entire project into a shutdown/deletion workflow affecting every resource, API, access binding, and service inside it. A project typically has a **pending deletion/recovery period** under Google Cloud policy; the action does not necessarily purge all physical resources instantaneously. Never treat clicking Delete as absolute proof that all billing stopped immediately. Inspect resource status and subsequent billing reports.

**Do not delete the project** if it belongs to a shared class, organization, long-term assigned lab environment, or contains resources with unclear ownership. In those cases, clean up only the resources you created and hand the project back to its owner.

## 11. Final check and recording results

Complete this table before finishing the lab:

| Item | What to prove | Self-check status |
|---|---|---|
| Project | Project ID and project number recorded accurately | ☐ |
| Resource hierarchy | Know which organization/folder the project belongs to, or that none exists | ☐ |
| IAM | Operator account permissions verified | ☐ |
| Billing | Billing linkage and budget monitoring mechanism checked | ☐ |
| Location | Bucket region recorded and distinguished from zone/parent location | ☐ |
| Data creation | `lab-note.txt` uploaded and read back successfully | ☐ |
| Data cleanup | Sample object and bucket deleted or handed over per policy | ☐ |
| Project cleanup | Retained project inventoried or transitioned to pending deletion | ☐ |
| Cost | Billing/budget reviewed; aware of potential reporting latency | ☐ |

**Success criteria:** you created and verified a sample project/resource accurately, identified the chosen location, and returned the environment to its intended state: either **a clean reusable learning project**, or **a dedicated lab project requested for deletion with verified status**.

## 12. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Create project button missing | Missing permissions or blocked by policy/quota | Check account/organization; use an assigned project |
| `PERMISSION_DENIED` on CLI call | Missing role on project, folder, billing, or bucket | Verify identity and exact permissions; ask admin for least-privilege grant |
| Bucket creation says name unavailable | Bucket name is globally unique and already taken | Choose a new unique name within the same project |
| Cannot select desired location | Organization constraint or service does not support that choice | Pick a policy-permitted location and document the change |
| Project created but services fail to work | Invalid billing, disabled APIs, quotas, or organization policy | Check each prerequisite via Console and read commands |
| Cannot delete bucket | Remaining objects/versions, retention/hold, or missing permissions | Inventory objects and policies; delete only data you own |
| Project disappears after deletion | Project is in shutdown phase / excluded from default list | Check lifecycle state and recovery process if authorized |
| Charges still appear after cleanup | Billing reporting lag or other billable resources/SKUs | Review reports by project, service, and usage date; check for leftover resources |

## 13. Self-check questions

**1. When creating a project in the Console, is the Location field necessarily the region of the bucket you will create?**  
**Answer:** no. Location on the project creation screen normally refers to the **organization/folder parent** in the hierarchy. A bucket's region is selected separately when creating the bucket.

**2. How do Project ID and project name differ?**  
**Answer:** project ID is the unique identifier used across APIs/CLI; project name is the display name. Project number is another distinct numeric ID assigned by Google.

**3. Why is deleting only `lab-note.txt` insufficient to conclude the lab is completely cleaned up?**  
**Answer:** the bucket still exists, and there may be other objects or versioning/soft-delete retention; additionally, the project might contain resources from other services. You must inventory and verify across the lab scope.

**4. Does a budget alert guarantee a project cannot accrue charges beyond the budget?**  
**Answer:** no. An alert is a signal for the project owner to notice and act; you must proactively limit and clean up resources.

**5. Should you delete a project shared by a team just to finish an individual lab?**  
**Answer:** no. Delete only your own resources per granted permissions, or ask the project owner for guidance. Deleting an entire project is reserved for verified dedicated lab projects.

**6. Must a Cloud Storage bucket and a Compute Engine VM in the same project share the same location?**  
**Answer:** no. A bucket has its own location while a VM selects a zone; choices are governed by architectural requirements and organization policies.

## Takeaways

- **Project is the governance unit**, while **region/zone is the deployment location choice** per resource type; do not confuse parent location during project creation with data region.
- **Commands must always bind to the right project and resource name** before acting, especially when deleting.
- **IAM, billing, APIs, location, and retention policies** are part of the resource lifecycle, not just creation-time settings.
- **Cleanup is a mandatory step of any cloud lab**: inventory → delete resources you created → verify results → handle the project according to ownership → check billing.

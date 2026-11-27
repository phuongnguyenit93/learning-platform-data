# Project ID, project number, and resource naming rules

In Google Cloud, a human-readable name like **Retail Production** is not enough to unambiguously identify the resource to manage. When deploying virtual machines, creating VPCs, granting IAM permissions, enabling APIs, or viewing costs, you must know which **project** is being used and which components that service uses to identify resources. This lesson focuses on three commonly confused concepts: **project name**, **project ID**, and **project number**; then expands to naming rules and resource uniqueness scopes.

This is foundational knowledge for upcoming Google Cloud hands-on lessons: organizing projects, IAM access control, deploying Compute Engine/GKE/Cloud Run, storing data, automating releases, and monitoring reliability as well as costs.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish project name, project ID, and project number, and know which fields are mutable.
2. Check whether a project ID follows **syntactic rules** and understand why valid syntax does not guarantee project creation will succeed.
3. Look up a project ID and project number via the Google Cloud console or `gcloud`.
4. Read a resource identifier to point out the project, service, region/zone, and resource name.
5. Design a naming convention that helps prevent deploying to the wrong environment, simplifies IAM auditing, and supports cost allocation.

## 1. Where does a project sit in the resource system?

In Google Cloud, a **project** is the fundamental unit for creating and managing most service resources. A project ties together API enablement, access control, quota management, and cost accounting. Within an organization, a project can sit directly under the **organization** or under a **folder**; service resources are created inside the corresponding project.

```text
Organization
└── Folder (can have multiple levels)
    ├── Project: retail-dev-01
    │   ├── VPC network: retail-dev-vpc
    │   ├── VM: web-01 (in a zone)
    │   └── Cloud Run service: api (in a region)
    └── Project: retail-prod-01
        ├── VPC network: retail-prod-vpc
        └── VM: web-01 (can reuse the same VM name as in the dev project)
```

The diagram only illustrates ownership and hierarchy. **The name `web-01` does not by itself indicate which project the VM belongs to**. To identify a specific VM, you need the project and zone as well; in systems using global internal DNS, there is also a project-level uniqueness constraint on VM names.

In operations, targeting the wrong project can lead to deploying into production, applying an IAM policy in the wrong place, or billing costs to another unit. Therefore, the project ID must be part of your context when running commands and troubleshooting incidents.

## 2. Three identifiers of a project

Suppose a team operates the following illustrative project:

| Attribute | Example value | Meaning | Who chooses? | Mutable after creation? |
| --- | --- | --- | --- | --- |
| **Project name** (display name) | `Retail Production` | Human-readable label in the admin UI | Project creator | **Yes** |
| **Project ID** | `retail-prod-01` | Unique project identifier string across Google Cloud | Chosen by creator or system-suggested | **No** |
| **Project number** | `123456789012` | Unique numeric ID assigned by Google Cloud | Google Cloud | **No** |

The values above are **examples** only and do not assert that such a project exists or that the project ID is available.

### Project name: for human readability

The project name is a display name and does not need to be unique. It can be changed when organizational needs change. According to project creation rules, the name is **4–30 characters** long, supporting letters, numbers, spaces, and certain allowed punctuation; the name must end with a letter or number.

APIs generally do not use the project name as an identifier key. Renaming `Retail Production` to `Retail Core Production` does not change the project ID or project number.

### Project ID: user-chosen identifier

The project ID is a unique string across **all of Google Cloud**, for example `retail-prod-01`. This is the value typically passed via the `--project` flag in `gcloud`, in SDK configurations, Terraform, API paths, and some resource names.

The project ID is **immutable after the project is created**. A used ID, even from a deleted project, cannot be reused for a new project. Therefore, choose an ID suitable for long-term use that does not depend on employee names, temporary tasks, or business secrets.

### Project number: system-generated identifier

The project number is a unique numeric code automatically assigned by Google Cloud and is read-only. Users cannot choose this number when creating a project. Some APIs and Google-managed identities use the **project number**, especially in canonical Cloud Resource Manager resource names and default service account emails.

For example, the default Compute Engine service account (when created) typically has an email matching the pattern:

```text
PROJECT_NUMBER-compute@developer.gserviceaccount.com
```

With the illustrative project number in the table, this pattern yields `123456789012-compute@developer.gserviceaccount.com`. Do not substitute `retail-prod-01-compute@...`: those are two different types of identifiers. Whether default accounts are created also depends on enabled APIs/services and the project lifecycle.

> **Key point:** Project name serves human readers; project ID is the creator-chosen identifier key; project number is the Google Cloud–assigned identifier key. A project has **one ID and one number**, and different services require these two values in different ways.

## 3. Rules for creating a project ID

Google Cloud enforces the following requirements for a **project ID**:

- **6–30 characters** long.
- Consists only of **lowercase letters a–z**, **digits 0–9**, and **hyphens `-`**.
- **Starts with a letter** and **does not end with a hyphen**.
- **Globally unique across Google Cloud**; an ID that has ever been used, even in a deleted project, is no longer available.
- Does not contain restricted strings, such as `google` or `ssl`. Problematic strings like `undefined` or `null` should also be avoided.

The regular expression below only checks **length and character set**; it cannot check whether the ID is already taken or on Google Cloud's restricted list:

```regex
^[a-z][a-z0-9-]{4,28}[a-z0-9]$
```

| Proposed value | Assessment | Reason |
| --- | --- | --- |
| `retail-prod-01` | Valid syntax | Lowercase, 6–30 characters, starts with a letter and ends with a digit |
| `retail-dev-02` | Valid syntax | Suitable for another environment; availability must still be checked |
| `Retail-Prod` | Invalid | Contains uppercase letters |
| `2-retail-prod` | Invalid | Starts with a digit |
| `retail_prod_01` | Invalid | Contains an underscore `_` |
| `retail-prod-` | Invalid | Ends with `-` |
| `app01` | Invalid | Only 5 characters long |
| `google-retail-prod` | Invalid | Contains the restricted string `google` |

**Valid syntax ≠ project can be created**: the name may already be owned, previously used, or subject to additional constraints. You must let Google Cloud validate it during project creation, while also checking project-creation permissions and organization policies.

A project ID can appear in URLs, API paths, logs, or resource names. Never put **passwords, tokens, personal information, or sensitive data** into a project ID, project name, or resource names.

## 4. Looking up a project's ID and number

### Via the Google Cloud console

Open the [Google Cloud console](https://console.cloud.google.com/) and select the right project in the project picker. The **Welcome** page displays the project name, project ID, and project number. If you manage multiple projects, you can search in **Manage resources**.

### Via the Google Cloud CLI

The following commands only illustrate how to look up information. They require `gcloud` to be installed, authenticated, and the account to have permissions to view projects.

```bash
# List projects visible to the current account.
gcloud projects list --format="table(projectId,projectNumber,name)"

# View details of a project by ID.
gcloud projects describe retail-prod-01

# Extract only the project number for integrations requiring the numeric ID.
gcloud projects describe retail-prod-01 --format="value(projectNumber)"

# Check the default project in the current gcloud configuration.
gcloud config get-value project

# Check the active identity.
gcloud auth list
```

If `gcloud projects describe` reports that the project does not exist or cannot be accessed, the cause could be a **wrong ID, nonexistent project, or missing permissions**. Do not jump to the conclusion from an error message that the ID has definitely never been used.

When working on a specific project, you can set the default project:

```bash
gcloud config set project retail-dev-01
```

However, before an important command, pass the project **explicitly** to reduce reliance on the current configuration:

```bash
# Read-only listing of VMs in the dev project.
gcloud compute instances list --project=retail-dev-01
```

Setting `gcloud config` only changes the CLI context; it **does not automatically grant IAM permissions** and does not move resources between projects. For CI/CD pipelines, specify the project explicitly in each deployment step and verify the executing identity.

## 5. Multi-layered resource identifiers

There is no single naming rule that applies uniformly across Compute Engine, VPC, GKE, Cloud Run, Cloud Storage, and databases. A full identifier typically combines:

1. **Project** owning or used to look up the resource.
2. **Service and resource type** (VM, VPC, subnet, Cloud Run service, bucket...).
3. **Location scope** if the service uses a region or zone.
4. **Resource name** following the service's own rules.

For example, the Compute Engine API identifies a VM by the path:

```text
projects/retail-prod-01/zones/asia-southeast1-b/instances/web-01
```

Where:

| Component | Value | Interpretation |
| --- | --- | --- |
| `projects/retail-prod-01` | `retail-prod-01` | Project ID |
| `zones/asia-southeast1-b` | `asia-southeast1-b` | Zone containing the VM |
| `instances/web-01` | `web-01` | VM name within the scope enforced by the service |

Providing only `web-01` is not enough to know which VM it is. A similar name can exist in another project or zone, depending on DNS configuration and resource type rules.

Cloud Run API v2 uses the resource name pattern:

```text
projects/retail-prod-01/locations/asia-southeast1/services/api
```

Here `locations/asia-southeast1` indicates a **region**, not a zone. For some Cloud Run methods, the project component accepts either **project ID or project number**. Do not assume every Google Cloud API accepts both: read the documentation for the exact API and field. For example, Compute Engine REST `instances.get` specifies the `project` parameter as the project ID.

### Uniqueness scope of resource names

| Resource type | Distinguishing scope | Examples and notes |
| --- | --- | --- |
| Project | Across all of Google Cloud | `retail-prod-01` must be globally unique |
| Compute Engine VPC network | Project-wide (global resource) | `retail-vpc` can be created in another project |
| Compute Engine subnet | Per region within a project | Requires project + region + subnet name |
| Compute Engine VM | Per zone within a project; **with DNS exceptions** | The same VM name can be used in two zones when using Zonal DNS; with global DNS configuration, VM names must be unique within the project |
| Cloud Run service | Per region within a project | Requires project + region + service name |
| Cloud Storage bucket | **Entire Cloud Storage namespace** | Bucket `retail-assets-demo-01` can only belong to one owner at a time, even across different projects |

Compute Engine has a common naming rule: **1–63 characters**, lowercase letters, digits, and `-`; starts with a lowercase letter and ends with a letter or digit (unless documentation for that resource type specifies otherwise). Do not apply this rule to buckets, BigQuery datasets, or Cloud Run services because each service has its own constraints.

Cloud Storage is a common exception: **bucket names must be unique across the entire bucket namespace**, not just within a project. A URI like `gs://bucket-name/path/to/object` addresses an object; the bucket component in the URI does not itself indicate the owning project. Cloud Storage buckets also have their own character set and naming limits, different from project IDs.

### Distinguishing logical names from system-assigned identifiers

In addition to project numbers, many services have **internal IDs/UIDs** for resources or deployment revisions. For instance, a Compute Engine VM has a `name` field and a system-assigned `id` field. These are not the project ID or project number. When analyzing incidents, state clearly whether you are referring to the **project number**, **instance ID**, or **service account ID** to avoid looking up the wrong entity.

## 6. Naming conventions for multi-environment systems

An organization can organize projects by product, environment, and permission boundaries:

| Environment | Project name | Illustrative project ID | Resource suggestions |
| --- | --- | --- | --- |
| Development | Retail Development | `retail-app-dev-01` | `retail-dev-vpc`, VM `web-01` |
| Staging | Retail Staging | `retail-app-stg-01` | `retail-stg-vpc`, Cloud Run `api` |
| Production | Retail Production | `retail-app-prod-01` | `retail-prod-vpc`, Cloud Run `api` |

Note that the examples only represent a **naming convention** and do not guarantee that the IDs or bucket names are available.

A reference pattern:

```text
<product>-<optional-component>-<environment>-<sequence>
retail-app-prod-01
retail-data-dev-01
```

When designing a convention:

- Choose **stable** components such as product, business domain, and environment; avoid embedding owner/employee names in IDs.
- Standardize abbreviations `dev`, `stg`, `prod`; include the environment in the ID to reduce the chance of selecting the wrong one.
- Check the 30-character project ID limit before adding department codes, regions, or sequence numbers.
- Add **region/zone** codes only where location truly needs to be expressed; a project ID does not imply the project only operates in one region.
- Attach appropriate **labels** (team, environment, cost center) for filtering and cost allocation; do not try to encode every piece of governance metadata into an immutable name.
- Record the **project name ↔ project ID ↔ project number** mapping, owner, environment, and billing account in your infrastructure management system.
- For IAM, grant permissions to the right identities on the right resource scope, following the **principle of least privilege**. Clean naming syntax is not a substitute for access control.

## 7. Real-world scenario: pipeline deploys to the wrong project

Suppose a team has two projects `retail-app-dev-01` and `retail-app-prod-01`, both containing a Cloud Run service named `api`. An engineer wants to deploy a new revision to development, but the current `gcloud` configuration points to production.

**Problem:** A command that only specifies `--service=api` or relies on the default project may target the wrong environment. Having the same service name does not mean it is the same resource.

**How to target accurately:**

1. Confirm the target project ID is `retail-app-dev-01`.
2. Check the identity running the command and its permissions on the dev project.
3. Verify the exact region, such as `asia-southeast1`.
4. When listing or deploying, specify `--project=retail-app-dev-01` and `--region=asia-southeast1`.
5. Record the project ID, project number, region, and service name in the release record for traceability.

Example **read-only** checks before deploying:

```bash
gcloud config get-value project
gcloud projects describe retail-app-dev-01 --format="value(projectNumber)"
gcloud run services describe api \
  --project=retail-app-dev-01 \
  --region=asia-southeast1
```

If the service does not yet exist in the dev project, recheck the project/region before creating a new one. Do not work around this by renaming existing production resources or attempting to deploy to another project without confirmation.

**Connection to IAM and costs:** A CI account may have permissions across multiple projects, so a command succeeding does not mean it ran in the right environment. Moreover, costs are primarily accounted per resource-using project and linked billing account; choosing the right project keeps cost reports and quotas separated between dev and prod.

## 8. Misconceptions to avoid

| Misconception | Correction |
| --- | --- |
| “Changing the project name changes the project ID” | The display name can change; the project ID stays the same |
| “A project ID matching the regex is guaranteed available” | Global uniqueness, prior usage history, and restricted strings must still be checked |
| “The project number is the trailing digits in the project ID” | The project number is assigned by Google, independent of your ID convention |
| “Every resource must have a globally unique name across Google Cloud” | Scope varies by service, resource type, and location; buckets are a globally unique example |
| “Every API accepts project ID and number interchangeably” | Check the exact API specification for which value each field accepts |
| “Selecting a project in the console means the CLI uses that project” | Console and `gcloud` maintain separate contexts; check CLI configuration |
| “The project number is a secret credential for authentication” | It is an identifier, **not a credential**; access is governed by IAM and authentication mechanisms |
| “Putting `prod` in the name is enough to protect production” | You also need IAM, release controls, project isolation, and appropriate policies |

## 9. Self-check

**Question 1.** Project `retail-dev-01` has its display name changed from “Retail Dev” to “Retail Development”. Which two values remain unchanged?

<details>
<summary>Answer</summary>

The project ID and project number. Only the project name changes.
</details>

**Question 2.** Can two different projects both have a VM named `web-01`? Can they both have a bucket named `retail-shared-assets`?

<details>
<summary>Answer</summary>

Two VMs with the same name can exist in two different projects because VM name scope is not Google Cloud–wide. Two Cloud Storage buckets cannot simultaneously share the same name within the global bucket namespace.
</details>

**Question 3.** An API reports the service identifier `projects/123456789012/locations/asia-southeast1/services/api`. What is the `123456789012` component here, and when should you look it up again?

<details>
<summary>Answer</summary>

In this scenario, it is an illustrative **project number**. When reusing it in another CLI command or API, look up the corresponding project ID and check whether that API accepts the ID, the number, or both.
</details>

**Question 4.** Why might `retail-prod-01` pass syntax checks yet still fail to create?

<details>
<summary>Answer</summary>

Because project IDs must be globally unique and cannot be reused if previously used; additionally, project creation depends on permissions and organization policies.
</details>

## Official References

- [Google Cloud — Create projects](https://cloud.google.com/resource-manager/docs/creating-managing-projects): project name, ID, number, and ID rules.
- [Google Cloud — View and update projects](https://cloud.google.com/resource-manager/docs/view-update-projects): identifying project details via console and CLI.
- [Google Cloud — Resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy): the project's place in the resource system.
- [Compute Engine — Naming resources](https://cloud.google.com/compute/docs/naming-resources): syntax and uniqueness scope of Compute Engine resource names.
- [Compute Engine — Global, regional, and zonal resources](https://cloud.google.com/compute/docs/regions-zones/global-regional-zonal-resources): rules for distinguishing resource locations.
- [Cloud Storage — About buckets](https://cloud.google.com/storage/docs/buckets): uniqueness scope and bucket naming syntax.
- [Compute Engine — Service accounts](https://cloud.google.com/compute/docs/access/service-accounts): identifying default service accounts that use the project number.
- [Cloud Run API v2 — Services](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services): service identifier pattern by project and location.

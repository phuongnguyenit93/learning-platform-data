# Organization, folder, project, and Resource Manager

Google Cloud offers many services such as Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL, and VPC. Before deploying an application, you need to determine **who owns the resources, which environment the resources belong to, who is allowed to operate on them, and which policies apply**. Google Cloud answers these questions through its resource hierarchy and the **Cloud Resource Manager** service.

This lesson belongs to the **Resource Hierarchy and Locations** chapter of the CLOUD_PROVIDERS_GCP module. It serves as the foundation for organizing projects, applying IAM, planning VPCs, deploying workloads, automating releases, monitoring reliability, and controlling costs in subsequent sections.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of `Organization`, `Folder`, `Project`, and service resources in Google Cloud.
2. Distinguish the governance scope of the resource hierarchy from billing accounts, geographic locations, and application runtime services.
3. Describe how IAM policies and Organization Policies are applied and inherited.
4. Use the Console or `gcloud` to explore the structure and create folders/projects with appropriate permissions.
5. Propose a practical structure for a development team with dev, staging, production environments, and centralized governance needs.

## 1. What is the resource hierarchy?

The **resource hierarchy** is a parent–child structure used to manage Google Cloud resources. In an enterprise organization, the typical order is:

~~~mermaid
flowchart TD
    O["Organization<br/>organizations/123456789012"]
    FP["Folder: Production<br/>folders/234567890123"]
    FN["Folder: Nonproduction<br/>folders/345678901234"]
    FC["Folder: Commerce<br/>folders/456789012345"]
    PP["Project: shop-prod<br/>shop-prod-example-2026"]
    PD["Project: shop-dev<br/>shop-dev-example-2026"]
    VM["Compute Engine VM"]
    RUN["Cloud Run service"]
    DB["Cloud SQL instance"]
    O --> FP
    O --> FN
    FP --> FC
    FC --> PP
    FN --> PD
    PP --> VM
    PP --> RUN
    PP --> DB
~~~

**Note:** Names and identifiers in the diagram are examples only. An organization can contain projects directly; folders are optional. Folders can contain nested folders and projects. Projects contain resources of services such as Compute Engine, Cloud Run, GKE, and Cloud Storage.

Foundational rules:

- **Every object has exactly one direct parent** in the hierarchy, except the root node. For example, a project cannot simultaneously reside under two folders.
- **Policies can be inherited downward.** Access permissions granted at the organization or folder level can apply to the resources below.
- **Project is the central working unit.** Most Google Cloud services require a project to enable APIs, create resources, and define the management scope.
- **Not every account has an organization.** When using Google Cloud with a personal account, projects can sit at the top of the hierarchy. Using folders requires an organization.
- **The hierarchy is not a network or geographic topology.** A `Production` folder does not mean all VMs reside in the same region, and projects in the same folder are not automatically networked together.

You can think of the hierarchy like an enterprise directory system: the organization is the company, folders are departments or environment groups, and a project is where you deploy a workload or a set of services with a shared owner.

## 2. Organization: enterprise-wide governance level

An **Organization** represents the enterprise or entity that owns Google Cloud resources. It is the root node of a structured hierarchy and is linked to **Google Workspace** or **Cloud Identity**. An organization has a resource ID such as `organizations/123456789012`.

Typical roles of an organization:

- Establish centralized ownership: projects belong to the enterprise rather than depending solely on the creator.
- Grant permissions to shared governance teams such as security, audit, and operations.
- Apply organization-wide governance rules using Organization Policy.
- Provide a starting point for organizing folders by business unit, engineering team, or environment.

For example, the company Atlas has **Security**, **Platform**, and **Commerce** teams. The Security team can be granted appropriate audit permissions at the organization level; the Commerce team receives narrower deployment permissions on its own folder.

### An organization is not synonymous with a billing account

A **Cloud Billing account** is responsible for payment and is linked to projects eligible to use billable services. A billing account **is not a folder** and **does not sit inside the Organization → Folder → Project tree**. An organization can have multiple billing accounts; multiple projects can be linked to the same billing account if configuration and permissions allow.

Therefore:

- **Hierarchy** answers: who owns the resources, and what governance scope do they belong to?
- **IAM/Organization Policy** answers: who can do what, and what rules constrain the resources?
- **Cloud Billing** answers: where are project costs recorded, tracked, and paid?
- **Region/zone** answers: in which infrastructure location are resources placed or served?

These four concerns are related, but they must be configured separately.

## 3. Folder: grouping projects to apply policies and delegate permissions

A **Folder** is an optional organizational layer beneath an organization or another folder, with an identifier such as `folders/234567890123`. Folders do not run containers, VMs, or databases; they group projects and child folders for management.

For example, an enterprise might choose:

~~~text
Organization: atlas.example
├── Production
│   ├── Commerce
│   │   ├── Project: atlas-shop-prod
│   │   └── Project: atlas-payment-prod
│   └── Analytics
│       └── Project: atlas-analytics-prod
├── Nonproduction
│   └── Commerce
│       ├── Project: atlas-shop-dev
│       └── Project: atlas-shop-staging
└── Platform
    └── Project: atlas-network-hub
~~~

This structure provides three benefits:

1. **Environment-based governance:** production projects receive the same production rule set from the `Production` folder.
2. **Team delegation:** Commerce administrators can be granted permissions within the Commerce folder without needing permissions across the entire organization.
3. **Logical scaling:** create new projects under the appropriate folder to inherit existing policies.

A folder is not an absolute isolation boundary. If someone is granted broad permissions at the organization level, those permissions can still be inherited down to the Commerce folder. Creating a new folder **does not automatically remove** permissions inherited from higher levels.

**When should you use folders?** When you have multiple projects sharing policies, owner groups, or permission delegation needs. For a small experimental project, adding multiple folder layers may only introduce unnecessary complexity.

## 4. Project: the unit of deployment, access control, and service management

A **Project** is where most Google Cloud resources are created and managed: VMs, Cloud Run services, GKE clusters, buckets, databases, VPC configurations, and many other resources. It is also the standard scope for enabling APIs, granting IAM permissions, tracking quotas, and accounting for usage.

A project has three attributes that are easy to confuse:

| Attribute | Illustrative example | Meaning |
| --- | --- | --- |
| **Project ID** | `atlas-shop-prod-2026` | Chosen by the creator; must be globally unique and cannot be changed after creation. Frequently used in CLI/API. |
| **Project number** | `701234567890` | Automatically assigned by Google Cloud, immutable; used by certain APIs and service accounts. |
| **Project name** | `Atlas Shop - Production` | Editable display name; not used as a stable identifier key. |

A project also has a lifecycle state, a parent attribute, and labels. For example:

~~~json
{
  "projectId": "atlas-shop-prod-2026",
  "projectNumber": "701234567890",
  "name": "Atlas Shop - Production",
  "parent": {
    "type": "folder",
    "id": "456789012345"
  },
  "labels": {
    "environment": "production",
    "team": "commerce"
  },
  "lifecycleState": "ACTIVE"
}
~~~

This is an **illustrative data structure example**, not an actual response from a Google Cloud account.

### Why separate projects?

Consider a retail application with Cloud Run, Cloud SQL, and Cloud Storage. If dev and production share a project:

- Deployment and operational permissions are harder to separate.
- It is difficult to manage quotas, APIs, budgets, and costs per environment.
- The risk of accidentally modifying production resources increases.

Separating `atlas-shop-dev`, `atlas-shop-staging`, and `atlas-shop-prod` isolates the management scope, access control, budgets, and resources. However, **separating projects does not mean complete network isolation**: cross-project connectivity can still be established using appropriate networking features, such as Shared VPC, and both permissions and connectivity must be configured explicitly.

A project can change its parent via a valid move operation, but moving changes the scope of inherited policies. It should not be treated merely as rearranging folders.

## 5. What does Cloud Resource Manager manage?

**Cloud Resource Manager** provides management interfaces for the hierarchy, including the Console, Google Cloud CLI, and Cloud Resource Manager API. It is used to:

- Find, create, list, describe, update, and manage the lifecycle of projects/folders based on granted permissions.
- Explore parent relationships among organizations, folders, and projects.
- Manage IAM policies for the corresponding hierarchy objects.
- Support moving projects/folders when conditions and permissions allow.

Resource Manager does not replace all other governance services:

| Task | Appropriate service/mechanism |
| --- | --- |
| Manage organizations, folders, projects, and parent–child relationships | **Cloud Resource Manager** |
| Grant roles to principals | **IAM** along with resource access policies |
| Enforce governance constraints | **Organization Policy Service** |
| Enable APIs for a project | **Service Usage** |
| Link projects to billing accounts and track costs | **Cloud Billing** |
| Search and inventory multiple cloud resource types | **Cloud Asset Inventory** |
| Choose locations to run VMs, clusters, or store data | Service-specific **region/zone/location** configuration |

For example: creating a project with Resource Manager only creates a management unit. To run an actual Cloud Run application, you also need to ensure deployment permissions, enable required APIs, link billing when required, build artifacts, and configure appropriate networking or IAM.

## 6. Policy inheritance along the hierarchy

The greatest strength of the hierarchy is the ability to set permissions and governance rules at the right level and let them apply down to the resources underneath.

### 6.1. IAM allow policy: granting permissions top-down

Suppose:

~~~text
Organization
└── Folder: Production
    └── Folder: Commerce
        └── Project: atlas-shop-prod
~~~

- The group `security-auditors@example.com` is granted an appropriate read-only role at the organization level.
- The group `prod-observers@example.com` is granted appropriate log-viewing permissions at the Production folder level.
- The application's deployment service account is granted only the necessary roles on the `atlas-shop-prod` project.

At the `atlas-shop-prod` project, IAM allow bindings on **the project itself** combine with allow bindings **inherited from ancestors**. Effective roles also depend on binding conditions, resource types, and other access control mechanisms.

> **Caution:** Removing a role from a project's IAM policy does not revoke permissions that are still granted from the organization or folder. To change inherited permissions, you must review the policy where the permission was granted.

Do not grant `roles/owner` or broad administrative permissions at the organization level to all developers just for convenience when deploying an application. Use groups, narrowly scoped roles, dedicated service accounts, and the smallest resource scope required for the job.

### 6.2. IAM Deny and Organization Policy are two different mechanisms

**IAM Deny** can block specific permissions even when corresponding allow bindings exist; deny policies also have their own rules for scope and inheritance.

**Organization Policy** governs **allowed configuration conditions** for resources. For example, an enterprise can restrict certain deployment locations or control public IP address usage according to supported constraints. The effective policy depends on the constraint type, attachment point, inheritance behavior, and enforcement rules; you cannot deduce the outcome merely by adding rules together.

| Question | Related mechanism |
| --- | --- |
| Which group is allowed to view project configuration? | IAM allow policy |
| Need to block a principal from using a specific permission? | IAM Deny |
| Is creating a configuration type that violates company rules allowed? | Organization Policy |
| Can that person actually access the resource? | Check **effective permissions**, including allow, deny, conditions, and related controls |

### 6.3. Three safety rules

1. Attach shared permissions at the **highest level actually needed**: organization-wide auditing at the organization, production operations at the Production folder, and single-application deployment at the application project.
2. Separate **hierarchy administration** roles (creating projects, managing folders) from **workload administration** roles (modifying Cloud Run, GKE, Cloud SQL).
3. Before moving a project or changing folders, verify effective permissions, Organization Policies, and operational dependencies; policies from the new ancestor may cause the application to behave differently.

## 7. Hands-on hierarchy exploration with gcloud

The commands below are run in Cloud Shell or a terminal with **Google Cloud CLI** installed. You must be signed in with the right account and have permissions to view/create the corresponding resources. IDs in the examples are hypothetical; replace them with real IDs before running.

### Step 1: Check the account and organization

~~~bash
gcloud auth list
gcloud organizations list
~~~

`gcloud organizations list` lists organizations accessible to the current account. If the list is empty, the account may not belong to an organization or may lack view permissions; do not automatically conclude that an organization does not exist.

### Step 2: View folders and projects

~~~bash
# Direct child folders of the organization
gcloud resource-manager folders list --organization=123456789012

# Direct child folders of a folder
gcloud resource-manager folders list --folder=234567890123

# Projects the account can list
gcloud projects list

# Describe a project
gcloud projects describe atlas-shop-prod-2026
~~~

Observe the project ID, project number, parent, and state fields. Listing results reflect the **visibility permissions** of the account, so they may not be complete for the entire enterprise.

### Step 3: Create a sample folder and project

The following example runs **commands that create real resources** if executed with an authorized account. Only run them in an authorized organization/lab, and choose an unused project ID.

~~~bash
# Create the Commerce folder under the organization
gcloud resource-manager folders create \
  --display-name="Commerce" \
  --organization=123456789012

# Use the actual folder ID returned above to create a project
gcloud projects create atlas-shop-dev-2026 \
  --name="Atlas Shop Dev" \
  --folder=456789012345 \
  --labels=environment=dev,team=commerce

# Verify the project
gcloud projects describe atlas-shop-dev-2026
~~~

If there is no folder, an organization-owned project can be created directly under the organization using `--organization=ORGANIZATION_ID` instead of `--folder=FOLDER_ID`. Some personal accounts can create projects without an organization. Do not pass both parent flags at the same time.

Creating a folder typically requires permissions on the parent; creating a project also requires project-creation permissions on the parent. Being allowed to use services inside a project **does not automatically** grant permission to create new projects.

### Step 4: View IAM policy at the project level

~~~bash
gcloud projects get-iam-policy atlas-shop-dev-2026
~~~

This command is useful for viewing the **direct allow policy** attached to the project. To evaluate effective permissions, you also need to inspect bindings inherited from folders/organization and related policies; viewing the policy at the project level once is not enough to prove whether a principal has or lacks a permission.

### Step 5: Complete the prerequisites for running services

Before running a VM, creating a database, or deploying Cloud Run/GKE, verify in sequence:

1. A billing account is linked to the project if required by the service.
2. Required APIs are enabled via Service Usage.
3. The deploying account has appropriate roles; the runtime service account also has least-privilege permissions.
4. Region/zone, VPC, security rules, and quotas meet the workload's requirements.
5. Labels and cost/log/metrics monitoring mechanisms fit the environment.

The hierarchy determines the **governance scope**; it does not automatically perform these five steps.

## 8. Design scenario: multi-environment e-commerce

Atlas operates a retail application consisting of a web API on Cloud Run, event processing, Cloud SQL, and an image storage bucket. The team wants to:

- Avoid accidentally deploying dev changes to production.
- Allow Security broad auditing access, while developers only deploy to their assigned environments.
- Manage costs and quotas separately per environment.
- Use shared network infrastructure when needed, while still managing IAM at each project.

A sound design:

| Level | Sample resource | Purpose |
| --- | --- | --- |
| Organization | `atlas.example` | Ownership and company-wide policies |
| Folder | `Production` | Rules protecting customer-facing systems |
| Subfolder | `Production/Commerce` | Delegation for the Commerce team in production |
| Project | `atlas-shop-prod` | Cloud Run, database, and storage for the production application |
| Folder | `Nonproduction` | Policies for experimentation and testing |
| Project | `atlas-shop-dev`, `atlas-shop-staging` | Separate development and staging environments |
| Folder | `Platform` | Governance for shared infrastructure services |
| Project | `atlas-network-hub` | Example where the Platform team manages central network infrastructure |

**Decision flow for a new workload:**

~~~mermaid
flowchart TD
    A["New workload arrives"] --> B{"Who owns and is responsible for it?"}
    B --> C["Choose organization and governance folder branch"]
    C --> D{"Does the environment need separate IAM, quota, cost, lifecycle?"}
    D -->|Yes| E["Create a dedicated project"]
    D -->|No| F["Evaluate reusing an existing project"]
    E --> G["Apply IAM and Organization Policy"]
    F --> G
    G --> H["Link billing, enable APIs, choose location, and configure network"]
    H --> I["Deploy, label, observe, and manage costs"]
~~~

The design above prioritizes separating dev/staging/production because they differ in permissions and operational requirements. It does not imply that every microservice must have its own project. In real designs, consider **ownership, required isolation level, quotas, permission model, cost, and lifecycle**.

### What happens when policies are applied?

Suppose a log-viewing role is granted to the on-call team at the `Production` folder. When the `atlas-payment-prod` project is created under that branch, the corresponding permission can be inherited without adding individual bindings to each project.

Conversely, if developers have edit permissions on the `Nonproduction` folder, placing a production project into that folder by mistake breaks the intended permission boundary. Therefore, **choosing the right parent when creating a project is a security and operational decision**, not merely a naming choice.

## 9. Common mistakes and how to avoid them

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Confusing project name with project ID | Scripts/APIs reference the wrong project | Use the immutable ID in automation; set display names for human readability |
| Granting overly broad permissions at organization | Permissions cascade down to many projects | Use narrow roles and attach them at the appropriate folder/project |
| Thinking a folder blocks inherited IAM | Users with higher-level permissions can still access resources | Inspect the full effective allow/deny policies |
| Treating a billing account like a folder | Flawed organizational model and cost allocation | Manage billing links and cost reporting separately |
| Putting all dev/prod in one project | Hard to separate permissions, quotas, costs, and lifecycle | Split projects by environment when clearly justified |
| Changing a project's parent without assessment | New policies may block deployments or widen access | Check IAM, Organization Policy, and dependencies before/after moving |
| Assuming projects in the same folder share a network | Applications fail to connect as expected | Design VPC, Shared VPC, routing, and firewalls explicitly |
| Assuming the Production folder determines data location | Workloads may end up in unwanted regions | Select and verify per-service locations; apply constraints where appropriate |

## 10. Self-check exercises

**Exercise 1.** The organization grants group A view access to resources across the company. Project X sits under the Production folder, but the project itself has no separate binding for A. Is A guaranteed to lose view access because the project does not declare this binding?

*Answer hint:* No. Allow bindings at the organization level can be inherited down to the project. Determining effective access also requires evaluating conditions, deny rules, and related access controls.

**Exercise 2.** The Commerce team needs dev and prod environments separated in terms of IAM and quotas. Should they create two folders, two projects, or two organizations?

*Answer hint:* Typically start with **two projects** separating the environments, placed under dev/prod folders matching the existing governance structure. Two organizations just for two environments usually adds unnecessary complexity.

**Exercise 3.** A project has the display name `Shop Production` and ID `atlas-shop-prod-2026`. After changing the display name, does CI/CD need to update the project ID value?

*Answer hint:* No. The project ID is independent of the display name and cannot be changed after creation.

**Exercise 4.** The Platform team moves a project from the Nonproduction folder to Production. What are two important things to review?

*Answer hint:* Effective IAM permissions after inheriting from the new ancestor and Organization Policies applied on the Production branch. Also check impacts on deployments, related quotas/configurations, and other dependencies.

**Exercise 5.** Is creating a project sufficient to deploy a Cloud Run application using Cloud SQL?

*Answer hint:* Not yet. You need billing/APIs as required, IAM for deployers and runtime, database resources, location, networking, security, usage limits, and operational observability.

## 11. Key takeaways for upcoming GCP lessons

- **Organization** defines enterprise-wide ownership and governance.
- **Folder** groups projects or child folders for policy inheritance and structured delegation.
- **Project** is the practical unit for using services and managing resources.
- **Cloud Resource Manager** is the toolset/API for orchestrating hierarchy nodes.
- **IAM**, **Organization Policy**, **Billing**, **VPC**, and **location** address different governance dimensions and must be combined at the right levels.

When creating any workload in upcoming lessons on Compute Engine, GKE, Cloud Run, storage, or databases, first ask: **which project does the workload belong to, which parent is the project under, who has permission to modify it, and what policies are currently in effect?** Answering those four questions provides a clear foundation for deployment, security, automation, observability, and cost optimization.

## Official References

- [About resource hierarchy — Google Cloud Resource Manager](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Resource Manager overview](https://docs.cloud.google.com/resource-manager/docs/resource-manager-overview)
- [Using resource hierarchy for access control — IAM](https://docs.cloud.google.com/iam/docs/resource-hierarchy-access-control)
- [Create folders](https://docs.cloud.google.com/resource-manager/docs/creating-managing-folders)
- [gcloud projects create](https://docs.cloud.google.com/sdk/gcloud/reference/projects/create)
- [gcloud resource-manager folders list](https://docs.cloud.google.com/sdk/gcloud/reference/resource-manager/folders/list)

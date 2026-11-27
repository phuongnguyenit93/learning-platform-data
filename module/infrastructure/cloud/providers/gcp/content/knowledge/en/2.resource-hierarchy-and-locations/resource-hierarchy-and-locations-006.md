# Designing projects for environments and development teams

In Google Cloud, deciding how many **projects** to create, where to place them in the resource tree, and whom to grant permissions directly impacts deployability, blast-radius isolation, cost governance, and security. An application can run fine when everything sits in a single experimental project, yet that organization usually becomes hard to govern as you add development teams, staging environments, production data, and release pipelines.

This lesson falls within **CLOUD_PROVIDERS_GCP**, laying the groundwork for using IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases in subsequent lessons. The goal is to design a project structure clear enough for teams to work independently and operate safely while still sharing necessary infrastructure capabilities.

After this lesson, you will be able to:

- Distinguish Organization, Folder, Project, service resources, and deployment locations.
- Choose project boundaries based on environment, owning team, and risk level.
- Propose an IAM, networking, billing, and monitoring structure across multiple projects.
- Establish naming conventions, labeling, and automated project creation.
- Recognize signs indicating that a project structure needs to be split or adjusted.

## 1. Project is the most important governance unit for a workload

A project holds resources such as Cloud Run services, Compute Engine VMs, Cloud Storage buckets, or databases. Each project has key characteristics:

| Component | Design significance |
|---|---|
| **Project ID** | Identifier used in APIs, CLI, and many resource names; must be globally unique across Google Cloud and cannot be changed after creation. |
| **Project number** | Numeric identifier assigned by Google Cloud, commonly seen in service agents and some permission configurations. |
| **Project name** | Display name for users; can be changed without altering the Project ID. |
| **IAM policy** | Attachment point for granting permissions to groups, users, and service accounts; still affected by permissions inherited from higher levels. |
| **APIs and quotas** | APIs are enabled per project; many quotas are tracked per project, service, and sometimes per region or zone. |
| **Billing** | A project is linked to an active Cloud Billing account to pay for billable resources. |
| **Lifecycle** | A project can be disabled, deleted, or moved in the resource tree; these operations carry wide impact. |

A project is a **useful governance and resource-separation boundary**, not an absolute security wall. Organization/Folder-level IAM can be inherited; service accounts can still be granted cross-project access; Shared VPC can allow multiple projects to share a network. Therefore, project structure, IAM, networking, and organization policies must be designed together.

### Resource tree and inheritance relationships

~~~text
Organization (enterprise)
└── Folder (governance group or environment)
    └── Folder (optional sub-grouping tier)
        └── Project
            ├── Cloud Run service
            ├── Compute Engine VM
            └── Cloud Storage bucket
~~~

- **Organization** represents the top-level enterprise governance scope when the enterprise has an Organization resource.
- **Folder** groups projects according to governance structure; folders do not directly contain VMs or databases.
- **Project** is the parent of many service resource types and is the standard deployment scope.
- **IAM** can be assigned at multiple levels. Permissions granted to a group on a Folder are generally inherited by child projects; assigning permissions on a project does not automatically remove inherited permissions.
- **Organization Policy** restricts how services or resources can be used, such as restricting allowed deployment locations. Its purpose differs from IAM: it constrains allowed configurations/behaviors, whereas IAM controls which identities may perform actions.

If an organization does not yet have an Organization resource, projects can still be created, but Folder-based governance and centralized policies are limited. For enterprise systems, set up an Organization before scaling to multiple production workloads.

## 2. Criteria for choosing project boundaries

Three factors usually drive the project-splitting strategy: **environment**, **ownership**, and **required isolation level**.

### Separating environments

Dev, staging, and production serve different purposes:

| Environment | Purpose | Governance principle |
|---|---|---|
| **Dev** | Frequent development and experimentation | More flexible permissions, replaceable resources, cost caps. |
| **Staging/UAT** | Integration testing, acceptance, and release validation | Configuration close enough to production to catch defects before release. |
| **Production** | Serving real users or live data | Strict permissions, approved changes, comprehensive logging and incident recovery. |

For critical applications, using a **dedicated project for production** is a sensible default. That way, deleting a resource, changing IAM, enabling an API, or exhausting quota in dev is far less likely to directly affect production.

Separating projects is only part of the solution: you must also separate deployment identities, secrets, data, and access permissions. Never bring sensitive production data into dev without proper anonymization or controls.

### Separating teams or workloads

One team may own multiple services, and one service may have a completely independent lifecycle from another. Use the following table to decide:

| Signal | Appropriate design direction | Reason |
|---|---|---|
| Two workloads have different owners, permissions, or risk levels | Separate projects per workload, at least in production | Separates accountability and reduces blast radius of mistakes. |
| Same team, small components released together sharing the same policies | Can share a project within each environment | Reduces project count and administrative overhead. |
| Independent cost accounting or quota management needed | Consider a dedicated project | Simplifies tracking costs and quota usage per workload. |
| Two applications need network communication | Do not have to be in the same project | Can use Shared VPC or controlled connectivity. |
| One application runs in multiple regions | Does not automatically require multiple projects | Region/zone is a resource location attribute; split projects only for operational or compliance needs. |
| Significantly different data sensitivity or compliance requirements | Prefer separate projects and matching policies | Simplifies restricting accessing identities, storage locations, and audit scope. |

There is no "one microservice = one project" rule for all systems. Creating too few projects causes overlapping permissions; creating too many makes bootstrap, IAM, networking, and monitoring workflows hard to maintain. Choose granularity based on **real accountability and risk boundaries**.

## 3. Three common organizational patterns

**Pattern A — environment first.** Production, staging, and dev folders hold the corresponding application projects. Useful when production controls differ sharply from non-production environments and the platform team wants to apply shared policies at the Folder level.

**Pattern B — product team first.** Payments, catalog, and analytics folders; each team holds its dev, staging, and prod projects. Useful when teams self-manage most of the application lifecycle and have domain-specific policies.

**Pattern C — hybrid.** Use top-level Folders by risk/environment, then group by team or workload; dedicate separate projects for shared capabilities like CI/CD, security logging, and networking. This is a practical starting point for many enterprises with multiple teams and environments.

Example of an enterprise with **Payments** and **Catalog** teams:

~~~text
Organization: example.com
├── Folder: production
│   ├── Project: acme-payments-prod
│   ├── Project: acme-catalog-prod
│   └── Project: acme-network-prod         (Shared VPC host)
├── Folder: nonproduction
│   ├── Folder: development
│   │   ├── Project: acme-payments-dev
│   │   └── Project: acme-catalog-dev
│   ├── Folder: staging
│   │   ├── Project: acme-payments-stg
│   │   └── Project: acme-catalog-stg
│   └── Project: acme-network-nonprod      (Shared VPC host)
└── Folder: shared-services
    ├── Project: acme-cicd
    └── Project: acme-security-logs
~~~

These names are illustrative only. In real deployments, the **Project ID must be globally unique**, so you may need to add a company code, product code, or suitable suffix. Do not create Folders for individual teams unless those Folders serve a concrete permission-delegation or policy-enforcement purpose.

With the layout above:

1. Changes in `acme-payments-dev` do not directly touch resources in `acme-payments-prod`.
2. The Payments team can be granted development permissions in the dev project; production deployment permissions belong to a narrowly scoped pipeline identity.
3. Production projects inherit policies from the production Folder.
4. The platform team manages shared networking and monitoring; each application team is accountable for its own workload.
5. When a team adds a workload with a distinct risk profile, an independent project can be added without reorganizing all existing projects.

## 4. Designing access control alongside projects

Creating projects first and granting ad-hoc permissions later often leads to development environments being able to affect production. Define **who operates**, **who deploys**, and **who only views** while sketching the resource tree.

| Identity or group | Dev | Staging | Production |
|---|---|---|---|
| Development team | Permissions appropriate to build and experiment | Mostly view, some testing actions | View necessary operational info; no default edit permissions |
| CI/CD pipeline | Deploys using a dev-specific identity | Deploys using a staging-specific identity | Only approved release identities deploy |
| Platform/SRE team | Platform administration per responsibilities | Platform administration per responsibilities | Controlled, auditable operational permissions |
| Security/audit team | Access for review | Access for review | View logs and required configs, avoiding unnecessary edit rights |

Principles:

- **Grant permissions to groups** instead of individuals wherever possible; manage group membership through HR/identity processes.
- **Least privilege**: prefer predefined roles tailored to each service, and consider custom roles when needed; avoid broadly granting `Owner` or `Editor` to an entire team for convenience.
- **Smallest reasonable scope**: grant at a Folder only if it applies to every project below; if only one project needs access, assign at that project or resource.
- **Separate human and workload identities**: use dedicated service accounts for apps or pipelines; avoid sharing a single service account with permissions across every environment.
- **Limit long-lived service account keys**: prefer short-lived credentials, workload identity federation, or impersonation where appropriate.
- **Check inheritance before expanding permissions**: a member who already holds permissions from the Organization or Folder does not need duplicate bindings at the project.

For example, a CI/CD system located in `acme-cicd` can still deploy into `acme-payments-prod` via a dedicated identity granted the necessary permissions **on the target project and related resources**. Simply residing in a shared-services project does not grant CI/CD permission to deploy everywhere. Some deployment flows also require permission to act as the application's runtime service account, so both permission layers must be verified.

IAM and Organization Policy complement each other. Someone with valid IAM permissions still cannot create a resource that violates an enforced Organization Policy constraint. When moving a project to a different Folder, review both **inherited permissions and inherited policies**, as project behavior may change.

## 5. Sharing infrastructure while preserving responsibility boundaries

### Networking and Shared VPC

Every application project does not need its own independent VPC. With **Shared VPC**, a **host project** manages VPCs and subnets; linked **service projects** can use the host's subnets if granted appropriate permissions.

~~~text
acme-network-prod (host project)
└── production-vpc
    ├── subnet-app (region A)
    └── subnet-data (region A)
         ↑                     ↑
acme-payments-prod       acme-catalog-prod
 (service project)        (service project)
~~~

This lets the networking team centrally manage IP ranges, routing, and firewall rules while application teams deploy workloads in their own projects. Projects participating in Shared VPC must meet Google Cloud requirements, including that host and service projects belong to the same Organization. Sharing a VPC does not replace network access governance: you must restrict who may use which subnets, which connectivity rules are permitted, and how egress traffic is controlled.

If production and nonproduction require strict isolation, using separate host projects or VPCs per scope is easier to govern. Do not bridge networks across environments just because applications share source code.

### Data, secrets, and shared services

- **Production data** should reside in projects and resources subject to production policies. Cross-project access is opened only to identities that genuinely need it, with least privilege.
- **Secrets** must be separated per environment; never reuse the same credentials for dev and prod.
- **Artifact Registry, builds, and CI/CD** can be centralized, while identities reading artifacts and deploying remain scoped per target workload.
- **Cloud Logging and Cloud Monitoring** can aggregate or display data across projects with appropriate configuration and permissions; consider routing necessary log copies to centralized storage for auditing.
- **Cloud KMS**, backups, and encryption key management must be designed around security and recovery requirements; never assume resources in different projects cannot access each other.

## 6. Separating project boundaries from geographic locations

A project is a globally scoped governance object; **a project does not have a single region**. Each service has its own location scope:

| Resource type | Example location scope | Decisions required |
|---|---|---|
| Compute Engine VM | Zone | Choose zone, scalability, and fault-tolerance strategy. |
| Cloud Run service | Region | Choose a region close to users and aligned with data dependencies. |
| GKE cluster | Zonal or regional depending on configuration | Choose availability architecture and node/control plane placement. |
| Cloud Storage bucket | Region, dual-region, or multi-region per configuration | Choose data storage location based on latency, durability, and data policy. |
| Databases | Varies by service, usually with region and HA options | Choose data placement, replicas, and recovery approach. |

For example, `acme-payments-prod` can contain Cloud Run in one region and a bucket in a location compliant with storage rules. If data must stay within a permitted geographic area, inspect the actual location of **each service** and configure Organization Policies where appropriate. Merely putting “asia” or “eu” in a project name creates no location restriction.

Split into separate projects by region only when doing so brings clear benefits, such as needing independent governance permissions, billing, quotas, or failure domains. For many applications, a single production project holding resources in multiple regions is sensible.

## 7. Naming conventions, labels, and costs

A simple convention is:

~~~text
<organization>-<workload>-<environment>[-<suffix>]
~~~

Illustrative examples: `acme-payments-dev`, `acme-payments-stg`, `acme-payments-prod`. In real systems, names must follow Google Cloud's character/length rules and guarantee global uniqueness for the Project ID. Because the Project ID is immutable after creation, review names before provisioning resources.

Apply consistent **labels** to support search and cost analysis, such as:

~~~yaml
environment: prod
team: payments
service: checkout
cost_center: commerce
managed_by: terraform
~~~

Labels are metadata; they are **not** an IAM mechanism. When tag-based policy conditions are needed, use **Resource Manager tags** appropriately rather than assuming labels create security boundaries.

For costs, the design should include:

1. **Billing account**: link each project to the appropriate billing account; a project links to only one Billing account at a time.
2. **Budgets and alerts**: configure appropriate cost alerts for production and nonproduction. Budgets do not automatically cap or stop resource consumption when exceeded.
3. **Billing export**: if detailed analysis by project, team, service, or time is needed, export billing data to BigQuery and build reports.
4. **Quotas**: check service quotas in the right project, region/zone, and enforcement tier before deploying heavy load. Quotas are not a substitute for budgets.
5. **Ownership**: every project needs a person/team responsible for approving costs, cleaning up resources, and responding to alerts.

## 8. Automating project creation with Infrastructure as Code

As the number of projects grows, manual creation via the Console easily introduces drift in permissions, labels, APIs, and logging. A “project factory” pipeline can standardize the steps: select Folder → assign Project ID → link Billing → enable required APIs → assign IAM → configure networking, logs, policies, and monitoring.

Minimal Terraform example:

~~~hcl
resource "google_project" "payments_dev" {
  name            = "Payments Dev"
  project_id      = var.payments_dev_project_id
  folder_id       = var.dev_folder_id
  billing_account = var.billing_account_id

  labels = {
    environment = "dev"
    team        = "payments"
    service     = "checkout"
  }
}

resource "google_project_service" "cloud_run" {
  project            = google_project.payments_dev.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_iam_member" "developers_read" {
  project = google_project.payments_dev.project_id
  role    = "roles/viewer"
  member  = "group:payments-devs@example.com"
}
~~~

This snippet illustrates how configurations link together. Before applying, you need a valid Folder, Billing account, valid Project ID, and a Terraform identity with sufficient permissions; service-specific IAM must also be considered. `roles/viewer` in the example only represents project read access, **not Cloud Run deployment permissions**. Production setups also need state configuration, deletion protection, review workflows, and shared governance modules.

Recommended provisioning workflow:

1. Requester declares owner, workload, environment, data classification, target region, and budget.
2. Pipeline validates naming rules, labels, Folder, and applicable policies.
3. Terraform changes are reviewed; production requires explicit approval per organizational process.
4. Project is created with minimal IAM and APIs; services are deployed by an environment-specific identity.
5. System re-verifies IAM, policies, networking, logging, labels, and costs after provisioning.

For production, permissions to create projects and change Billing accounts must be tightly governed because they can substantially expand resource usage and cost exposure.

## 9. Design scenario: two teams releasing independently

An e-commerce company has Payments and Catalog teams. Payments processes sensitive transactions; Catalog frequently updates UI and product data. Both want to release daily without letting dev bugs affect production.

**Appropriate approach:** split `payments-dev/stg/prod` and `catalog-dev/stg/prod` into six application projects. Production projects sit under the production Folder; direct edit permissions are restricted, and deployment identities are separated by application. Both applications can use a production Shared VPC operated by the platform team, while connectivity and data access permissions must be approved. Logging and billing are aggregated centrally while still tracking costs per project.

If Catalog later introduces an image-processing system with high quota demands and an independent release cycle, it can be split into its own project without splitting the entire e-commerce platform. Conversely, two small Payments components with the same operations team, security profile, and release cadence can remain in the same project within each environment.

This approach balances fault isolation, team autonomy, operational cost, and shared infrastructure reuse. However, achieving the intended isolation requires **IAM, networking, data, and pipelines to enforce the designed boundaries**.

## 10. Checklist for reviewing a project design

Before creating a project or promoting a workload to production, check:

- [ ] Each project has a clear purpose, environment, owner, and cost accountability contact.
- [ ] Production is appropriately separated from dev and staging, including service accounts and secrets.
- [ ] Folders reflect where shared policies or permissions are needed; do not create hierarchy levels just to make a diagram look neat.
- [ ] Permissions are granted to groups with least-privilege scope; inherited permissions have been reviewed.
- [ ] Cross-project connections and Shared VPC usage are documented, authorized, and controlled.
- [ ] Deployment locations are verified per service and against data storage requirements.
- [ ] Appropriate labels, budget alerts, logging, monitoring, and quota-tracking plans are in place.
- [ ] Project creation, API enablement, IAM management, and config changes are repeatable via code.
- [ ] Project IDs and any hard-to-reverse choices are reviewed prior to creation.

**Applied exercise:** Design a Folder/Project tree for three teams—Web, Payments, and Analytics—each with dev and production. Payments requires stricter access control; Analytics requires an approved data storage region; the platform team owns shared networking and CI/CD. For each project, identify the owner, environment, Billing account, primary IAM groups, and data placement. Then explain when projects can be shared, when they should be split, and how changing a Folder policy affects child projects.

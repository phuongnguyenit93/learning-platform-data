# Organizing a Project Factory and Project Provisioning Workflow

A development team needs a new Google Cloud project to test an API on Cloud Run. If each team creates projects, enables APIs, grants IAM, and links billing in their own way, the organization quickly ends up with projects without clear owners, missing cost labels, overly broad permissions, and hard-to-control network configurations. A manual approval process spanning multiple departments can also drag on, pushing developers to find workarounds.

A **project factory** is the process and tooling for **provisioning projects from approved templates**. A valid request flows through validation, approval, automated project creation, baseline configuration, verification, and handover to the requesting team. When implemented properly, a project factory speeds up onboarding while maintaining organizational governance controls.

This lesson belongs to the **Organization Governance** chapter of the **CLOUD_PROVIDERS_GCP** module. It bridges the resource hierarchy, IAM, and VPCs with practical operations such as creating environments for Compute Engine, GKE, Cloud Run, Cloud Storage, or databases, while supporting release automation, reliability monitoring, and cost management.

After this lesson, you will be able to:

- Describe the inputs, outputs, and operational steps of a project factory.
- Build a workflow for requesting, risk-assessing, approving, provisioning, and handing over a project.
- Choose the appropriate Folder, billing account, IAM, networking, APIs, and policies for a workload.
- Understand how to standardize projects using Terraform, CI/CD, and policy as code.
- Design post-provisioning checks, configuration drift detection, and project retirement workflows.
- Evaluate when a dedicated project is needed versus when an existing project can be used.

## 1. What Is a Project Factory, and What Is It Not?

A **Google Cloud project** is the unit containing most service resources, with a Project ID, Project number, IAM policy, APIs, quotas, and billing linkage. It sits in the **Organization → Folder → Project** hierarchy. A project has only one parent at a time; certain permissions and policies from the parent can be inherited down to the project and child resources.

A **project factory** typically includes:

| Component | Responsibility | Output |
|---|---|---|
| **Request portal** | Collects purpose, owning team, environment, data classification, budget, and networking needs | Structured request |
| **Validator** | Verifies required fields, naming rules, Folder/billing, permissions, quota limits, and policies | Validation report or rejection reason |
| **Approval flow** | Identifies authorities accepting risk, cost, and access permissions | Traceable decision |
| **Provisioner** | Creates the project and applies baseline configuration via API/Terraform | Project and foundation resources |
| **Post-check** | Reads back IAM, billing, APIs, logging, networking, labels, policies, quotas | Verification results and evidence |
| **Project catalog** | Records owner, purpose, status, review date, and configuration | Manageable project inventory |
| **Lifecycle workflow** | Change requests, owner changes, periodic reviews, decommissioning, and deletion | Project governed until end of life |

A project factory is **not a standalone Google Cloud product that you simply enable**. Enterprises can build it themselves with Terraform and pipelines, use modules from Cloud Foundation Toolkit/Cloud Foundation Fabric, or use the Enterprise foundations blueprint as a reference architecture. Implementations vary, but the goal is **consistent baseline projects given the same inputs and policies**.

## 2. Designing the Foundation Before Automating Project Creation

You cannot have a reliable project factory if the organization has not agreed on hierarchy, IAM, billing, and network connectivity. Decisions at the **landing zone/cloud foundation** layer must be defined first.

### Sample Resource Hierarchy

~~~text
Organization: example.com
├── Folder: production
│   ├── Project: shop-orders-prod-01
│   └── Project: shop-catalog-prod-01
├── Folder: nonproduction
│   ├── Folder: development
│   │   ├── Project: shop-orders-dev-01
│   │   └── Project: shop-catalog-dev-01
│   └── Folder: staging
│       └── Project: shop-orders-stg-01
└── Folder: shared-services
    ├── Project: org-project-factory
    ├── Project: org-network-prod
    ├── Project: org-network-nonprod
    ├── Project: org-cicd
    └── Project: org-security-logs
~~~

This diagram is **illustrative**; Project IDs must be checked for global uniqueness before creation. An organization does not necessarily need a Folder per team. You should only create Folder levels when shared IAM/Organization Policies, environment rules, or clear administrative delegation are needed.

**Separation of duties:** the project factory manages provisioning and baseline configuration. The platform team administers networking, the security team establishes guardrails, finance manages billing, and application teams own workloads. Permission to create projects does not imply permission to bypass organizational policies.

### Decisions to Standardize

| Decision | Example Rule | Rationale |
|---|---|---|
| **Project boundary** | Production separated from nonproduction; sensitive workloads get dedicated projects | Limits blast radius and permission scope |
| **Parent Folder** | `production` for production, `development` for dev | Inherits appropriate IAM and Organization Policies |
| **Billing account** | By business unit or approved accounting model | Cost management and payment accountability |
| **Naming** | `<org>-<workload>-<env>-<suffix>` | Easy identification and lookup |
| **Owner** | One group responsible for operations and cost, with a backup owner | Prevents "orphaned" projects |
| **Labels/Tags** | `team`, `environment`, `cost_center`, `data_class` | Resource filtering, cost analysis, policy support |
| **IAM** | Least privilege, granted via Google Groups and workload identities | Reduces out-of-scope access |
| **Network** | Dedicated VPC or Shared VPC per environment | Consistent and secure connectivity paths |
| **APIs** | Enable only APIs required by the workload profile | Reduces operational scope and configuration surface |
| **Operations** | Logging, Monitoring, alerting, audit, budget | Enables incident detection and cost tracking |
| **Lifecycle** | Review/expiration date for sandboxes, project retirement workflow | Avoids lingering unused resources |

**Labels** are metadata only; they must not be treated as IAM boundaries. If policies require **Resource Manager tags**, the project factory must create or attach tags through the proper mechanism, accounting for inheritance and tag management permissions.

## 3. Determining When a New Project Is Needed

Not every service deployment request requires its own project. Use these questions:

1. Does the workload have a **production** environment or sensitive data that must be isolated from dev/staging?
2. Does the owning team require independent IAM, networking, quotas, billing, or lifecycle?
3. Are there organization policies, data location requirements, or audit requirements different from existing workloads?
4. Are the services released, recovered, and monitored independently?
5. If sharing a project, would a misoperation or quota exhaustion in workload A significantly impact workload B?

| Scenario | Guidance |
|---|---|
| A small microservice sharing the same team, policies, and lifecycle as an existing service | Consider keeping it in the existing project |
| Production API handling payments and experimental sandbox | Separate projects |
| Analytics team with distinct data/region and audit requirements | Consider a dedicated project |
| Workloads needing a shared VPC | Can use separate projects connected via Shared VPC if appropriate |
| Application running across multiple regions | Does not automatically require a separate project per region |

A project is a useful **governance** boundary, but it does not provide absolute isolation on its own. IAM inherited from Organization/Folder and cross-project access can still exist; the project factory must also configure appropriate IAM, data, and networking rules.

## 4. Designing a Machine-Validatable Request Form

A free-form request forces reviewers to ask follow-up questions repeatedly. Instead, standardize the request schema with agreed fields.

~~~yaml
# Example INTERNAL manifest for a project factory, not a Google Cloud API schema.
request_id: PRJ-2026-0042
workload: orders-api
environment: dev
owner_group: orders-team@example.com
technical_contact: orders-techlead@example.com
cost_center: commerce
billing_profile: engineering-nonprod
data_classification: internal
parent_profile: development
network_profile: shared-nonprod
requested_services:
  - run.googleapis.com
  - artifactregistry.googleapis.com
  - secretmanager.googleapis.com
region_preference: asia-southeast1
monthly_budget_usd: 250
review_date: 2027-02-28
business_reason: "Testing deployment of orders API on Cloud Run"
~~~

The provisioner must map each **profile** to approved Folder IDs, Billing account IDs, and network configurations. Do not trust a Folder ID or billing account entered directly by a requester without verifying permissions and policies.

### Pre-Approval Data Validation

- **Required fields:** workload, environment, owner group, cost center, data classification, review date.
- **Validity:** naming format, length, enum values, email/group format, request ID, and proposed Project ID.
- **Uniqueness:** request is not a duplicate submission; Project ID is not already taken.
- **Governance constraints:** production must map to the right Folder; network and billing profiles must be on the allowlist.
- **Data classification:** personal, sensitive, or location-restricted data requests require matching policies.
- **Scale and budget:** VM types, GKE node counts, Cloud Run concurrency, or services needing large quotas must be declared when required.
- **Identity and operations:** the owner Google Group is active and someone is accountable for incidents.

A Google Cloud Project ID is a **globally unique, immutable** identifier after creation. Under current rules, it is typically 6–30 characters, using lowercase letters, digits, and hyphens, starting with a letter, not ending with a hyphen, and avoiding restricted strings; once used, an ID cannot be reused even after project deletion. Therefore, the workflow must **pre-approve the final name** and avoid putting secrets in the Project ID or Project name.

## 5. Provisioning Flow from Request to Handover

~~~mermaid
flowchart TD
    A["Team submits request"] --> B["Validate schema, ID, profile, quota"]
    B --> C{"Valid?"}
    C -- "No" --> R["Return reason, request revisions"]
    R --> A
    C -- "Yes" --> D{"Matches approval matrix?"}
    D -- "No" --> E["Reject / escalate to authority"]
    D -- "Yes" --> F["Review Terraform plan and policies"]
    F --> G["Pipeline provisions project / billing / APIs / IAM / network"]
    G --> H["Post-check and update catalog"]
    H --> I{"Meets criteria?"}
    I -- "No" --> J["Remediate / block handover"]
    J --> H
    I -- "Yes" --> K["Hand over project, owner confirms"]
    K --> L["Periodic review / changes / retirement"]
~~~

Suggested governance states:

| Status | Meaning | Required Evidence |
|---|---|---|
| `REQUESTED` | Request has been logged | Request ID and submitter data |
| `VALIDATED` | Fields and rules checked | Validation check report |
| `APPROVED` | Approved by authorized stakeholders | Approval ID and comments |
| `PROVISIONING` | Pipeline is applying configuration | Run ID, Terraform plan/apply logs |
| `VERIFIED` | Technical checks passed | Post-check verification record |
| `ACTIVE` | Handed over to owner | Owner confirmation, project ID/number |
| `CHANGE_REQUESTED` | Change requested for IAM, network, or billing | Pull request/change record |
| `RETIRING` | Decommissioning in progress | Data export plan and dependencies |
| `RETIRED` | Decommissioning completed per policy | Retirement and archival evidence |

The workflow should be **idempotent**: re-running with the same request ID and configuration must not create duplicate projects or repeatedly grant uncontrolled permissions. If project creation succeeds while API enablement fails, the record must reflect the partial state so it can resume or remediate safely rather than creating another project.

### Who Approves What?

| Scenario | Product Owner | Platform | Security | Finance/FinOps |
|---|---|---|---|---|
| Dev project using standard profile | Accountable for purpose | Confirms profile/technical fit | Automated policy checks | Pre-allocated budget |
| Production with internal data | Approves objective and accountability | Network architecture, operations | Access and data controls | Billing and budget |
| Sensitive workload or policy exception needed | Justifies need | Assesses feasibility | Approves time-bound exception | Assesses cost risk |
| Quota increase or billing change | Confirms need | Evaluates load and impact | Reviews if risk surface expands | Approves cost |

This is a **reference matrix**. Organizations must clearly define final decision-makers, request handling SLAs, and auto-approval thresholds so every sandbox does not wait on a review board.

## 6. Resource Bootstrap Sequence

A project factory pipeline can run in this sequence:

1. **Receive the approved manifest.** Lock governance-impacting parameters such as parent Folder, billing, environment, and network profile.
2. **Create the project with Cloud Resource Manager.** Record the Project ID and Project number; wait for the creation operation to succeed.
3. **Link the Cloud Billing account.** Ensure the pipeline identity has permission to link the chosen billing account.
4. **Configure labels/tags and guardrails.** Verify the project sits under the right Folder to inherit IAM/Organization Policies; apply project-level policies if needed.
5. **Configure baseline IAM.** Grant required permissions to the owner group, operations team, and CI/CD identity; avoid granting Owner/Editor to the entire team.
6. **Enable APIs per workload profile.** For example, Cloud Run requires `run.googleapis.com`; related services are enabled as needed.
7. **Connect networking.** Attach the project to the approved Shared VPC/VPC model; configure subnets and usage permissions per environment.
8. **Configure observability and cost controls.** Logging/Monitoring, required sinks/alerts, budgets, and cost-allocation metadata.
9. **Run post-checks.** Read back critical settings; test access using appropriate identities and verify baseline service calls.
10. **Hand over.** Register in the catalog, communicate Project ID, access permissions, deployment instructions, support contacts, and review schedule.

Not every project needs its own VPC, cluster, or database resources at creation time. The factory can provision a **baseline**, and then workload teams deploy application resources in their own pipelines.

**Note on APIs and service identities:** enabling APIs can create Google-managed service agents/service accounts. Certain APIs, IAM bindings, or subnets must be initialized in the right order; post-checks must wait for asynchronous resources to become ready before concluding failure.

## 7. Using Terraform as the Project Factory Engine

Terraform lets you declare configuration in code, generate a plan for review, and deliver changes via pipelines. You can use **Cloud Foundation Toolkit** or **Cloud Foundation Fabric** as a foundation instead of writing every module from scratch.

The following HCL example is a **minimal baseline for a dev project**. The Folder and Billing account have already been created by administrators; the Project ID must be valid and unique:

~~~hcl
terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

variable "project_id" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "billing_account_id" {
  type = string
}

variable "developer_group_email" {
  type = string
}

resource "google_project" "orders_dev" {
  name                = "Orders Dev"
  project_id          = var.project_id
  folder_id           = var.folder_id
  billing_account     = var.billing_account_id
  auto_create_network = false

  labels = {
    environment = "dev"
    team        = "orders"
    cost_center = "commerce"
    managed_by  = "terraform"
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])

  project            = google_project.orders_dev.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_iam_member" "developers_view" {
  project = google_project.orders_dev.project_id
  role    = "roles/viewer"
  member  = format("group:%s", var.developer_group_email)
}

output "created_project_id" {
  value = google_project.orders_dev.project_id
}
~~~

This snippet is **not a complete project factory**: it does not create budgets, Shared VPC attachments, log sinks, alerts, tag bindings, or deployment permissions. `roles/viewer` only illustrates how read access is granted; building/deploying Cloud Run requires **action-specific** permissions and an appropriate service account.

Practical notes when applying in production:

- The pipeline identity needs permissions to create projects under the parent, link billing, update IAM, and enable the corresponding APIs. Do not grant full Organization Admin just for convenience.
- For Terraform IAM, `google_project_iam_member` manages a single member of a role. By contrast, `google_project_iam_binding` is authoritative for the **entire role** and `google_project_iam_policy` is authoritative for the **entire allow policy** on the resource. Choosing the wrong one can overwrite bindings managed by other teams or Google.
- **Terraform state** may contain sensitive data; store it in a controlled backend, encrypted, with restricted IAM, and avoid committing state into Git.
- For production, add mandatory reviews, check plans for `destroy`/`replace` actions, enable deletion protection, and establish a recovery workflow.
- Only use vetted provider/module versions, and run `terraform fmt`, `terraform validate`, and `plan` before `apply` in real pipelines.

A basic GitOps pipeline:

~~~text
Approved request
→ Pull request adds project manifest
→ Schema / policy-as-code / lint checks
→ terraform plan
→ Owner + platform (+ security if needed) review
→ Pipeline uses dedicated identity for terraform apply
→ Post-provisioning verification
→ Record project ID, number, owner, status in registry
~~~

**Preventing out-of-band changes:** monitor drift between Terraform config and live state; inspect Audit Logs. If an emergency fix via Console is required, log a change record and bring the change back into code afterward.

## 8. Manual Provisioning to Understand the APIs, Then Automate

During training or when debugging a pipeline, you can test the following `gcloud` commands **in an authorized sandbox project**, using placeholder parameters:

~~~bash
PROJECT_ID="shop-orders-dev-01"
FOLDER_ID="123456789012"
BILLING_ACCOUNT_ID="000000-000000-000000"

# Create the project under an organization-managed Folder.
gcloud projects create "$PROJECT_ID" \
  --folder="$FOLDER_ID" \
  --name="Orders Dev"

# Link the approved billing account.
gcloud billing projects link "$PROJECT_ID" \
  --billing-account="$BILLING_ACCOUNT_ID"

# Enable required APIs matching the application profile.
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"

# Grant viewer access only for testing; do not grant Owner to the whole team.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="group:orders-developers@example.com" \
  --role="roles/viewer"

# Read back the project and policies after provisioning.
gcloud projects describe "$PROJECT_ID"
gcloud projects get-iam-policy "$PROJECT_ID"
gcloud billing projects describe "$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID"
~~~

These commands are **illustrative** and do not run against any real project in this lesson. They can create resources and incur charges if executed yourself. The Project ID and Billing account values are placeholders only; you need `resourcemanager.projects.create` on the parent and corresponding billing permissions. When using an automation service account, the project must be created under an allowed Organization/Folder; do not create "no organization" projects with service accounts.

In operational systems, ad-hoc CLI commands should be replaced by IaC modules with retries, status checks, and audit logging. Do not repeatedly re-run project creation with new IDs just to "work around" an undiagnosed error.

## 9. Project Factory IAM: Do Not Over-Privilege

At least **three identity groups** should be separated:

| Identity | Responsibility | IAM Principle |
|---|---|---|
| **Requester/owner group** | Requests and operates the workload after handover | Does not need organization-wide project creation permission |
| **Factory pipeline identity** | Creates projects, links billing, applies baseline IAM/APIs/metadata | Creation permission on designated Folders plus minimal additional permissions |
| **Application CI/CD identity** | Deploys Cloud Run, GKE, or Compute Engine inside provisioned projects | Scoped to target workload and environment |

For project creation, `roles/resourcemanager.projectCreator` is typically granted on the **parent** to the factory identity. For billing, permission to use the approved Billing account is needed (such as `roles/billing.user` depending on the permission model); operations such as updating IAM, APIs, budgets, or networking require appropriate permissions on those respective resources. Always calculate **effective permissions**, including inherited IAM, before adding roles.

Guardrails to standardize:

- Do not broadly grant `roles/owner` or `roles/editor` to all developers across all projects.
- Production deployment permissions belong on the CI/CD service account with proper approvals.
- Avoid long-lived service account keys when Workload Identity Federation or short-lived token mechanisms can be used.
- IAM on a Shared VPC host differs from IAM on a workload service project; connect only when allowed by the network profile.
- Avoid creating the `default` VPC automatically if the design requires controlled networking.
- Distinguish **Organization Policy** (behavior constraints) from **IAM** (principal permissions).
- Never store secrets, private keys, or personal data in request manifests, Terraform variables, or pipeline logs.

### Controlling Location and Network Policies

A project itself is not pinned to a single region. When a team must store data in a specific location, the factory must record the data profile, apply location Organization Policies where appropriate, and ensure application pipelines verify **per-resource locations**: Cloud Run region, VM zone, bucket location, database region.

In a Shared VPC model, the application project can be a **service project** while the host project owns the network/subnets. Attachment depends on Shared VPC requirements and permissions on both sides, not merely on two projects residing in the same Folder.

## 10. Lifecycle Billing, Quotas, and FinOps

### Controlled Billing Linkage

A project can only be linked to **one Cloud Billing account at a time**. The factory maps `cost_center`, environment, and business unit to an account approved by Finance. Project recipients must not arbitrarily switch Billing accounts outside a formal change workflow.

Suggested labels:

~~~yaml
team: orders
environment: dev
service: orders-api
cost_center: commerce
managed_by: terraform
~~~

Beyond labels, the registry must store metadata unsuitable for labels, such as owner email, approval timestamp, provisioning reason, review date, and ticket links.

### Budgets Are Not Always Hard Spend Limits

- **Alerts-only budgets** track actual or forecasted spend and send threshold alerts; by themselves, they **do not block** consumption when budgets are exceeded.
- **Spend cap budgets** can be used for **eligible services and limited scopes**, such as a single project and a corresponding service. They are not a universal hard limit across every service in a project; enforcement may have latency and overages can still occur.
- For multi-service projects, combine alerts, quotas, autoscaling settings, appropriate resource limits, and anomaly response workflows.
- For multi-dimensional analysis, export Cloud Billing data to BigQuery and build reports by project, label, service, and SKU.

Current documentation on [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets) and [spend caps](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps) details these differences; during implementation, verify which services are currently eligible.

### Quotas and Project Limits

The number of projects you can create is subject to **project quotas/limits** based on account and organization status. Projects pending deletion but not yet permanently purged may still count toward limits. Additionally, each API has its own quotas per project, region, or service tier.

If the factory processes many concurrent requests, you need to:

1. Rate-limit creation according to Resource Manager quotas.
2. Retry with backoff for transient errors, without endlessly retrying IAM or policy errors.
3. Use fixed request IDs and Project IDs to avoid duplicate creations.
4. Distinguish project quota exhaustion from Compute Engine, GKE, or Cloud Run quota exhaustion.
5. Evaluate quota increase requests before provisioning high-resource production workloads.

## 11. Post-Checks: When Is a Project Considered Handed Over?

Creating a Project ID is only part of the job. An `ACTIVE` record must have results from the following checks:

| Check | Acceptance Criteria | Verification Method |
|---|---|---|
| **Resource Manager** | Project exists, under correct parent Folder, in active state | `gcloud projects describe` or API |
| **Billing** | Linked to approved billing account | Billing API/Console |
| **Labels/Tags** | Correct environment, owner/team, cost center; tag policies where required | Read back metadata and tag bindings |
| **IAM** | Required groups/identities have least privilege, no out-of-profile roles | IAM policy, Policy Troubleshooter if needed |
| **Organization Policy** | No guardrail violations; policies inherited along the right branch | Org Policy API/Console |
| **API** | Only required services are enabled and ready | Service Usage API |
| **Network** | Correct VPC/subnet or Shared VPC service project; appropriate egress path | Check network config and run controlled connectivity tests |
| **Operations** | Logging, Monitoring, alerting/sinks at required level | Read back configuration and trigger sample test events |
| **Cost** | Budgets/alerts or eligible spend caps configured | Cloud Billing Console/API |
| **Registry** | Owner, deadline, project number, plan/apply run ID, ticket | Read internal project catalog |

For production, you may add security review checks, recovery paths, log and data retention requirements, or compliance evidence. For sandboxes, the baseline is lighter, though owner and deletion mechanisms are still mandatory.

**Handover** must clearly state: Project ID and Project number, where to find the project in the Console, which groups have access, how to request additional APIs/quotas, the corresponding deploy pipeline, how to view costs, and operational support channels. Never hand over a newly created project that the owner cannot access or without telling them the change workflow.

## 12. Changes, Drift Detection, and End of Lifecycle

A good project factory also handles **what happens after day one**.

### Change Requests

For example, a team wants to move from Cloud Run to GKE, increase quotas, use a new subnet, or add a storage region. Instead of making manual edits that drift from IaC, change requests should go through a manifest/pull request, impact assessment, plan, and proper approvals.

Change classification:

| Change | Sensitivity | Handling Approach |
|---|---|---|
| Update owner group, non-sensitive labels | Low | Validate and apply under control |
| Enable a new API | Medium, depending on API | Check quotas, service agents, cost, and data impact |
| Change production IAM or deployment service account | High | Platform/security review, verify inherited permissions |
| Move Folder or Billing account | High | Assess IAM/Org Policy, networking, billing, and limits |
| Delete project or disable billing | Very high | Verify dependencies, backups, and policy approvals |

**Drift** occurs when live configuration diverges from what is declared in IaC. Sources of drift include Console edits, out-of-band API calls, default updates, or service-managed changes. The project factory should schedule `terraform plan` or periodic drift detection; when differences appear, review before reconciling, and avoid automatically deleting live production resources.

### Project Retirement Workflow

When a sandbox reaches its expiration date or a workload is decommissioned:

1. Confirm with the owner, approvers, and any remaining dependent systems.
2. Inventory Cloud Storage, databases, secrets, service accounts, images, and pipelines.
3. Determine export/backup requirements and retention periods for data and logs.
4. Safely stop workloads; remove unnecessary permissions or connections.
5. Schedule deletion per internal policy and obtain final confirmation.
6. Execute deletion through the approved workflow; monitor status and recovery window if applicable.
7. Update the registry, billing records, and dependent systems.

Deleting a Google Cloud project generally puts it into a **pending deletion** phase before permanent removal; recovery windows and conditions depend on service mechanics. Never treat deletion as a backup method or a safe rollback strategy. For production, enabling deletion protection in IaC and dependency checks helps prevent accidents.

## 13. Real-World Scenario: Scaling from 3 to 20 Development Teams

An e-commerce company started with 3 teams creating projects manually via the Console. When scaling to 20 teams, several problems emerged:

- Many dev projects lacked clear owners, and Billing accounts were linked inconsistently.
- Support teams had to grant IAM manually, and some people kept Editor access after switching projects.
- Production and test projects were mixed in the same Folder, making policy enforcement difficult.
- Some Cloud Run services and databases lacked proper logs/alerts; invoices were hard to allocate.
- Developers waited days for environment creation, leading to shadow projects outside the process.

The platform team built a **project factory** with three profiles:

| Profile | Need | Standard Configuration |
|---|---|---|
| `sandbox` | Time-boxed experimentation | Development Folder, mandatory owner, budget alert, restricted permissions, auto-review |
| `nonprod-app` | Ongoing dev/staging | Environment Folder, group IAM, logging, dev CI/CD, nonproduction networking |
| `production-app` | Customer-facing | Production Folder, security/FinOps review, strict IAM, monitoring/alerts, auditing, approved production connectivity |

**Example request from the Orders team:** create a dev project to develop a Java API on Cloud Run and read test data from Cloud Storage. The requester selects `nonprod-app`, owner `orders-team`, cost center `commerce`, an organization-approved region, and an estimated budget of 250 USD/month.

The factory validates the inputs, generates a plan, obtains appropriate approvals, then creates `shop-orders-dev-01` under the development Folder, links billing, enables the required Cloud Run/Artifact Registry/Cloud Storage APIs, assigns IAM to the team and pipeline, configures networking/logging/monitoring, sets a budget alert, and hands it over. CI/CD then deploys the Java service into the new project; the project factory itself does not deploy the entire application.

**When the team goes to production**, they submit a request with the `production-app` profile; the factory provisions a new project under the production Folder and applies stricter policies. Production is never just changing a label `environment=prod` inside the dev project.

### Measuring Project Factory Effectiveness

Useful metrics:

- **Time from REQUESTED to ACTIVE**, split between approval wait time and pipeline execution time.
- **First-time success rate**, categorizing errors across schema/IAM/quota/CI.
- **Percentage of projects with valid owner, labels, and billing**.
- **Percentage of projects passing baseline post-checks** and time to remediate drift.
- **Count of expired unretired sandboxes**, inactive projects, and their costs.
- **Count of open policy exceptions** and resolution time.

The goal is reducing provisioning lead time **while maintaining governance evidence**. Optimizing only for the number of projects created per day while ignoring ownership, IAM, and cleanup increases both cost and risk.

## 14. Project Factory Design Checklist

- [ ] Organization/Folder tree, project profiles, naming conventions, and ownership model are agreed upon.
- [ ] Request schema includes environment, owner, billing, data classification, budget, and lifecycle.
- [ ] Rules exist to decide between creating a new project versus reusing an existing one.
- [ ] Approvers, SLAs, exceptions, and automation thresholds are defined.
- [ ] The pipeline identity only has permissions to create projects and baseline config within its required scope.
- [ ] Terraform plans are reviewed before apply, with a secure state backend and destroy protections.
- [ ] IAM, Organization Policy, network, API, logging, and billing configs follow each profile.
- [ ] The factory has idempotency, sensible retries, operation tracking, and partial-state handling.
- [ ] Post-checks verify resource hierarchy, IAM, billing, APIs, networking, and cost tracking.
- [ ] The project catalog stores owner, creation time, project ID/number, status, and review schedule.
- [ ] Workflows exist for changes, drift detection, sandbox retirement, and safe project deletion.

**Applied Exercise:** Design a project factory for an enterprise with Payments, Catalog, and Data teams. Each team needs dev, staging, and production; Payments handles sensitive data and Data needs storage location restrictions. (1) Draw the Folder/Project tree, (2) define three configuration profiles, (3) propose a minimal request schema, (4) describe the approval matrix, (5) outline the Terraform pipeline and post-checks, (6) propose how to retire sandboxes after 30 days, and (7) handle the failure scenario where the pipeline creates the project successfully but enabling the Cloud Run API fails. Explain how to keep the project factory resumable after failures without creating duplicate projects.

## Official Documentation References

- [Create and manage projects — Cloud Resource Manager](https://cloud.google.com/resource-manager/docs/creating-managing-projects) — creation permissions, Project ID, Folder, and quotas.
- [Manage projects and billing in your organization](https://cloud.google.com/resource-manager/docs/organization-resource-management) — organizing administrative permissions and billing.
- [Enterprise foundations blueprint](https://cloud.google.com/architecture/blueprints/security-foundations) — foundational architecture, GitOps/IaC, IAM, networking, and controls.
- [Landing zone design in Google Cloud](https://cloud.google.com/architecture/landing-zones) — foundational decisions when building an enterprise environment.
- [Terraform blueprints and modules for Google Cloud](https://cloud.google.com/docs/terraform/blueprints/terraform-blueprints) — project-factory module and foundation modules.
- [Terraform best practices: Working with resources](https://cloud.google.com/docs/terraform/best-practices/working-with-resources) — considerations when managing IAM with Terraform.
- [Terraform best practices: Operations](https://cloud.google.com/docs/terraform/best-practices/operations) — plans, reviews, and pipelines.
- [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets) — budget alerts.
- [Spend cap budgets](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps) — scope of services supporting spend cap mechanisms.

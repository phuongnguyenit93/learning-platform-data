# Landing Zone Project with IAM, VPC, and Budget

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners practice selecting services, securing resources, automating releases, and monitoring reliability and cost. In the **GCP Hands-On Projects** chapter, this lesson combines the foundational concepts into a **minimal landing zone** that can be verified and extended.

You take on the role of a platform team preparing a `sandbox` environment for a Java/Spring Boot application. Before deploying the application, the team must create **governance boundaries**, **least-privilege identities and permissions**, a **controlled private network**, and **cost budgets and alerts**. The infrastructure is described using **Terraform**; verification steps clearly distinguish between configuration existence and actual resource usability.

> **Important:** This is an infrastructure lab that can incur costs and requires organization/folder/billing account permissions. Only deploy into an authorized environment with a billing owner and resource limits. Examples use a new project and do not modify production IAM or firewalls. **An alerts-only Billing Budget is not a hard spending cap**: when thresholds are exceeded, services may continue running and continue incurring charges.

## 1. Requirements and Acceptance Criteria

A product team needs an `orders-sandbox` project to later deploy a Java API. The platform team is responsible for preparing the following components:

| Item | Technical Requirement | Acceptance Evidence |
| --- | --- | --- |
| Resource hierarchy | Lab project resides under a folder managed by the platform team, linked to a valid billing account | Project/folder ID, parent, billing association |
| IAM | Dedicated runtime service account; observer group has log-view access only; network group has network-view access only | IAM policy without indiscriminately granted Owner/Editor roles |
| Default network | Prevent creation of the default VPC for new projects when organization policy allows | Effective policy and VPC list without `default` |
| VPC | Create a custom-mode VPC, subnet in the selected region, non-overlapping CIDR | Network/subnetwork description |
| Firewall | Do not open SSH/RDP to the entire Internet; only lab rule with restricted source/target | Firewall rules list and review result |
| Private access | Enable Private Google Access on the subnet to prepare for VMs without external IPs | Subnet setting; not confused with IAM |
| Budget | **Single-project** budget, monthly period, with spend and forecast thresholds | Budget showing accurate scope, amount, and notifications |
| Automation | Reviewed Terraform plan, separately stored state, applied by an authorized identity | Plan, `terraform output`, subsequent plan shows no unexpected changes |
| Recovery | Scope-accurate resource cleanup runbook, protecting the project from accidental deletion | Resource list, approved destruction plan |

**MVP Scope:** do not create VMs, databases, clusters, or public load balancers; only build the boundaries so workloads can enter later. This reduces costs in the lab and avoids confusing the existence of a subnet with network verification via live traffic.

## 2. Target Architecture

~~~mermaid
flowchart TB
    ORG[Google Cloud organization]
    FOLDER[Folder: Hands-on Sandbox]
    PROJ[Project: orders-sandbox]
    SA[Service account: orders-runtime]
    GROUPS[IAM: observer + network groups]
    API[Enabled APIs]
    VPC[Custom VPC: orders-vpc]
    SUBNET[Subnet: orders-app, 10.42.0.0/24]
    FW[Ingress firewall: TCP 8080 limited to subnet]
    BUDGET[Monthly Billing Budget: project-scoped]
    BILL[Cloud Billing account]
    STATE[Bootstrap project + protected GCS state]

    ORG --> FOLDER
    FOLDER --> PROJ
    PROJ --> SA
    PROJ --> GROUPS
    PROJ --> API
    PROJ --> VPC
    VPC --> SUBNET
    VPC --> FW
    BILL --> PROJ
    BILL --> BUDGET
    BUDGET -.->|filters numeric project ID| PROJ
    STATE -.->|Terraform manages| FOLDER
    STATE -.->|Terraform manages| PROJ
~~~

### 2.1. Distinguishing Boundaries

- **Organization and folder:** inheritance boundaries for IAM and Organization Policy, suitable for setting security baselines across multiple projects.
- **Project:** where billing, quotas, API enablement, service accounts, and most resources are attached.
- **Service account:** the identity a workload uses to call Google APIs; not a deployer's personal account.
- **VPC/subnet:** network paths and internal IP ranges; does not authenticate users or grant permissions to access Google APIs.
- **Billing account/budget:** tracks costs across projects and can configure threshold alerts; not a firewall policy or quota.
- **Terraform state:** contains infrastructure metadata and may contain sensitive data; must use a protected backend with separate access control.

An enterprise-grade landing zone may add Shared VPC, organization-wide audit logs, DNS, Cloud NAT, SCC, KMS, VPC Service Controls, and a multi-environment structure. This lesson intentionally scopes down to **IAM, VPC, and budget** so learners understand each boundary before expanding.

## 3. Prerequisites

### 3.1. Prerequisites

You need:

1. A **Google Cloud organization** and permissions to create folders/projects within an authorized area. A personal account without an organization cannot reproduce the exact folder-level pattern of this lab.
2. An active Cloud Billing account, its billing account ID, and permission to link projects to the account.
3. A **pre-existing bootstrap project**, used as the default project for the Terraform provider and hosting the Cloud Storage bucket for remote state.
4. A **pre-created** Cloud Storage bucket for storing Terraform state, with Object Versioning, Uniform Bucket-Level Access, and Public Access Prevention enabled.
5. Terraform CLI and Google Cloud CLI; an execution identity capable of using Application Default Credentials (ADC), preferring service account impersonation or Workload Identity Federation for CI/CD.
6. An unused project ID and bucket name, an appropriate region, and a CIDR range that does not overlap with existing networks.
7. Google Groups addresses `lab-observers@example.com` and `lab-network@example.com` that **already exist** or are replaced with real groups in your organization.

Do not let Terraform **create its own backend bucket in the very state that needs that backend**. Create the bootstrap layer separately before initializing the foundation layer.

### 3.2. Permission Matrix for the Deployment Identity

| Task | Typical Required Role | Scope |
| --- | --- | --- |
| Create folder | `roles/resourcemanager.folderCreator` | Organization or parent folder |
| Manage organization policy for folder | `roles/orgpolicy.policyAdmin` | Managed folder |
| Create project | `roles/resourcemanager.projectCreator` | Organization or parent folder |
| Link billing | `roles/billing.user` and appropriate project billing management permission | Billing account + project |
| Enable APIs | `roles/serviceusage.serviceUsageAdmin` | Created project |
| Create VPC/subnet/firewall | `roles/compute.networkAdmin` and appropriate API permissions | Network project |
| Create service account | `roles/iam.serviceAccountAdmin` or equivalent custom role | Project |
| Assign IAM member to project | `resourcemanager.projects.setIamPolicy` permission from an appropriate IAM management role | Project |
| Create billing-account-level budget | `roles/billing.costsManager` or `roles/billing.admin` | Billing account |
| Read/write remote state | Least-privilege Cloud Storage permissions for state operations | Bootstrap state bucket |

This is a **summary of permissions for the lab**; do not grant all of them to a single long-lived identity in production. Platform teams can split them into *organization bootstrap*, *network foundation*, and *billing FinOps* to reduce blast radius. Broad permissions are only used during the foundation creation step; CI pipelines deploying applications later do not need Project Creator or Billing Admin.

For user ADC using the `google_billing_budget` resource via the Terraform Google provider, provider documentation requires configuring `billing_project` and `user_project_override = true` to use the appropriate quota project. That identity needs `serviceusage.services.use` on the bootstrap billing project.

### 3.3. Bootstrap APIs

Run under an authorized identity on the **bootstrap project** (not the not-yet-created lab project):

~~~bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  cloudbilling.googleapis.com \
  billingbudgets.googleapis.com \
  orgpolicy.googleapis.com \
  iam.googleapis.com \
  compute.googleapis.com \
  --project=BOOTSTRAP_PROJECT_ID
~~~

Some APIs also need to be enabled on source/target projects depending on the specific service. The `google_project_service` resource later enables APIs in the new project, but Terraform must have permission to manage Service Usage there. Do not use organization-wide Owner permissions to work around `403` errors in the lab.

## 4. Repository and State Layout

Example structure:

~~~text
gcp-landing-lab/
├── bootstrap/               # pre-created: GCS state bucket + CI identity
├── foundation/
│   ├── versions.tf
│   ├── providers.tf
│   ├── variables.tf
│   ├── hierarchy.tf
│   ├── iam.tf
│   ├── network.tf
│   ├── budget.tf
│   └── outputs.tf
└── environments/
    └── sandbox.tfvars
~~~

**You do not need to create these files inside the Java Learning module:** these are Terraform files that **learners will create in their own lab workspace**, not source files for this lesson.

### 4.1. Terraform and Provider Versions

`foundation/versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }

  backend "gcs" {
    bucket = "REPLACE_WITH_EXISTING_TFSTATE_BUCKET"
    prefix = "hands-on/landing-zone"
  }
}
~~~

The `~> 7.0` constraint is an **illustrative provider branch example**, not a guarantee that it is always the latest version. Choose a version compatible with your tested environment and commit `terraform.lock.hcl`. Replace the placeholder bucket with an existing bucket before running `terraform init`.

`foundation/providers.tf`:

~~~hcl
provider "google" {
  project               = var.bootstrap_project_id
  region                = var.region
  billing_project       = var.bootstrap_project_id
  user_project_override = true
}
~~~

The provider uses ADC. The `billing_project` setting here provides quota/billing context for API calls and **does not automatically attach a billing account to new projects**. The GCS backend and the provider may also use **two different authentication mechanisms**; verify state read/write permissions separately before planning.

### 4.2. Input Variables

`foundation/variables.tf`:

~~~hcl
variable "organization_id" {
  description = "Numeric organization ID."
  type        = string
}

variable "bootstrap_project_id" {
  description = "Existing project used for Terraform quota and state."
  type        = string
}

variable "billing_account_id" {
  description = "Cloud Billing account identifier."
  type        = string
}

variable "lab_project_id" {
  description = "Globally unique new project ID."
  type        = string
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "subnet_cidr" {
  type    = string
  default = "10.42.0.0/24"
}

variable "observer_group_email" {
  type = string
}

variable "network_group_email" {
  type = string
}

variable "budget_currency" {
  description = "Currency code of the billing account."
  type        = string
  default     = "USD"
}

variable "monthly_budget_units" {
  description = "Whole currency units for monthly alerts-only budget."
  type        = string
  default     = "50"
}
~~~

**Note on currency:** the `USD` and 50 values are only examples if the billing account actually uses USD. For accounts in another currency, obtain the actual currency code and adjust the amount accordingly; do not assume all Cloud Billing accounts in Vietnam use the same currency.

## 5. Resource Hierarchy: Folder, Organization Policy, and Project

### 5.1. Folder Isolating the Lab

`foundation/hierarchy.tf`:

~~~hcl
resource "google_folder" "sandbox" {
  display_name = "Hands-on Sandbox"
  parent       = format("organizations/%s", var.organization_id)
}
~~~

A folder is not a billing account. The value of `google_folder.sandbox.name` has the format `folders/NUMERIC_ID` and can be passed as `folder_id` for a project. The string Project ID and the numeric project number are different, and both are required by different APIs.

### 5.2. Guardrail Against Default Network

Create a policy at the **sandbox folder** so that new projects do not generate a default VPC when enabling the Compute Engine API:

~~~hcl
resource "google_org_policy_policy" "skip_default_network" {
  name   = format(
    "%s/policies/compute.skipDefaultNetworkCreation",
    google_folder.sandbox.name
  )
  parent = google_folder.sandbox.name

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
~~~

This policy requires the Organization Policy API and corresponding administrative permissions. **This is a boolean constraint, not a firewall rule**. It prevents the default network from being automatically created in child projects once the policy is in effect.

**Important ordering:** organization policies can take time to propagate. For strict environments, create the folder and policy in a **separate bootstrap/foundation stage**, verify the **effective policy** on the folder, and only then create the project. A dependency in Terraform only ensures the policy creation API call finishes; it **does not guarantee that all permissions/policies have propagated to every backend** immediately.

If you **do not have Organization Policy permissions**, do not skip the control and assume there is no default network. Ask an administrator to configure the policy on a parent folder, or separate the governance part from the lab project and verify before deploying.

### 5.3. Creating a Project with Billing, Labels, and Deletion Protection

Also in `foundation/hierarchy.tf`:

~~~hcl
resource "google_project" "sandbox" {
  name            = "Orders Landing Sandbox"
  project_id      = var.lab_project_id
  folder_id       = google_folder.sandbox.name
  billing_account = var.billing_account_id

  labels = {
    env        = "sandbox"
    owner_team = "platform"
    cost_area  = "training"
  }

  deletion_policy = "PREVENT"

  depends_on = [google_org_policy_policy.skip_default_network]
}
~~~

In the current branch of the Google provider, `deletion_policy = "PREVENT"` causes Terraform to reject unintended project destroy/recreate operations. This is not an absolute Resource Manager lock against all Google Cloud administrators, but it is a useful guardrail in the Terraform lifecycle. Changing the project ID triggers replacement; do not rename the project ID after running just for a prettier name.

Existing projects must be evaluated and **imported into state**, rather than creating duplicates that cause ID conflicts. A project with billing enabled and production data must never be accidentally managed or deleted by lab Terraform code.

### 5.4. Enabling Required APIs

~~~hcl
resource "google_project_service" "enabled" {
  for_each = toset([
    "compute.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.sandbox.project_id
  service            = each.value
  disable_on_destroy = false
}
~~~

`disable_on_destroy = false` avoids automatically disabling an API when the service resource is removed from Terraform state/config; this does not mean it is safe to delete any resources actively using the API. Review API needs and permissions before applying.

**Staged lab execution:** on the first run you can provision the folder/policy, verify the effective constraint, and then provision the project, APIs, and network. For standardized environments, split stacks into states with separate permissions rather than relying on `terraform -target` as a long-term workflow.

## 6. IAM Baseline: Principle of Least Privilege

### 6.1. Creating the Runtime Service Account

`foundation/iam.tf`:

~~~hcl
resource "google_service_account" "orders_runtime" {
  project      = google_project.sandbox.project_id
  account_id   = "orders-runtime"
  display_name = "Orders sandbox runtime"

  depends_on = [
    google_project_service.enabled["iam.googleapis.com"]
  ]
}
~~~

This is the identity for the **application that will run later**, not the identity running Terraform. It does not automatically have permissions to call Storage, Cloud SQL, or Pub/Sub. When adding workloads, grant specialized roles on **target resources** instead of project-wide `Editor`.

### 6.2. Separate Observer and Network Permissions

~~~hcl
resource "google_project_iam_member" "observers_logs" {
  project = google_project.sandbox.project_id
  role    = "roles/logging.viewer"
  member  = format("group:%s", var.observer_group_email)
}

resource "google_project_iam_member" "network_readers" {
  project = google_project.sandbox.project_id
  role    = "roles/compute.networkViewer"
  member  = format("group:%s", var.network_group_email)
}

resource "google_project_iam_member" "runtime_logs" {
  project = google_project.sandbox.project_id
  role    = "roles/logging.logWriter"
  member  = format(
    "serviceAccount:%s",
    google_service_account.orders_runtime.email
  )
}
~~~

Purpose of the three bindings:

- The **observers** group views logs within the scope of the granted role, without modifying VPCs or project IAM.
- The **network readers** group inspects network configuration, without inherently modifying firewalls.
- The runtime SA can write application logs via `logging.logWriter`; it cannot escalate to administrative privileges.

If the organization has sensitive data in Data Access logs or private log buckets, `roles/logging.viewer` does not mean viewing all content. Grant permissions based on data sensitivity and log views; never put secrets/passwords/tokens in logs.

**Prefer `google_project_iam_member`** when multiple teams or systems manage bindings together. The `google_project_iam_policy` resource is **authoritative** and can replace the entire policy; only use it if you control complete IAM ownership of the project. IAM Conditions and custom roles can be added once permission contracts are clear.

### 6.3. Permissions That Should Not Be Granted

Do not grant to the runtime:

- `roles/owner`, `roles/editor`, or `roles/resourcemanager.projectIamAdmin`.
- `roles/billing.admin`, `roles/resourcemanager.projectCreator`.
- Permission to create service account keys if the organization blocks it via Organization Policy.
- `roles/iam.serviceAccountTokenCreator` on other service accounts unless there is an approved impersonation flow.

CI/CD deployments should use Workload Identity Federation or short-lived service account impersonation; separate **deployer** permissions from **runtime** permissions. When someone leaves the team or a workload is compromised, the blast radius must be small enough to revoke cleanly.

## 7. VPC: Custom Mode, Subnet, and Minimal Firewall

### 7.1. Creating a VPC with Only Learner-Defined Subnets

`foundation/network.tf`:

~~~hcl
resource "google_compute_network" "orders" {
  project                 = google_project.sandbox.project_id
  name                    = "orders-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [
    google_project_service.enabled["compute.googleapis.com"]
  ]
}
~~~

A **custom-mode VPC** does not auto-create subnets in every region. This is the right choice when the network team wants explicit control over every CIDR. However, creating a custom VPC **does not delete the default VPC**; that is handled by the guardrail in section 5 and actual verification.

### 7.2. Creating a Subnet with Planned Addressing

~~~hcl
resource "google_compute_subnetwork" "orders_app" {
  project                  = google_project.sandbox.project_id
  name                     = "orders-app"
  region                   = var.region
  network                  = google_compute_network.orders.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}
~~~

The `10.42.0.0/24` example is for the sandbox. Before applying in a larger system, cross-check against on-premises ranges, VPN, VPC peering, Shared VPC, Private Service Access, and future address space reserves.

`private_ip_google_access = true` enables **VMs without external IPs** on the subnet to reach supported Google APIs via the appropriate path. It **does not grant IAM permissions**, does not guarantee all Google APIs are accessed over private endpoints, does not provide Internet egress, and does not create Cloud NAT. To verify it, a test workload must be deployed and both routing/DNS and IAM must be checked; the current MVP only verifies configuration.

### 7.3. Narrowly Scoped Illustrative Firewall

~~~hcl
resource "google_compute_firewall" "lab_app_internal" {
  project   = google_project.sandbox.project_id
  name      = "allow-lab-app-internal-8080"
  network   = google_compute_network.orders.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = [var.subnet_cidr]
  target_tags   = ["lab-app"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}
~~~

This rule only allows TCP `8080` from the chosen subnet range **to Compute Engine VMs with the network tag `lab-app`**. In the MVP no VM is created yet, so the rule **does not allow any application to connect immediately**. It is also not an IAM permission, does not apply to Cloud Run via VM network tag semantics, and does not automatically create routes or a port listener.

Google Cloud has an **implied deny ingress** and an **implied allow egress** at the VPC firewall level (unless altered by other policies/rules). Therefore, do not create inbound `0.0.0.0/0` rules for SSH `22` or RDP `3389`. If administrative SSH to VMs is needed later, evaluate IAP TCP forwarding, OS Login, firewall rules restricted to the appropriate IAP range, and separate IAM. Avoid treating network tags as a security boundary against actors who already have permission to manage VMs/tags; harden further with hierarchical firewall policies or service-account-based rules.

### 7.4. If Deploying Cloud Run or GKE Later

- **Cloud Run:** Direct VPC egress requires a subnet with sufficient IPs and egress configuration; it does not implicitly belong to a subnet like a VM. Cloud Run HTTP ingress is controlled separately.
- **GKE:** requires planning secondary IP ranges for Pods/Services if using a VPC-native cluster to avoid CIDR overlap; add separate firewall rules and Workload Identity Federation IAM.
- **Compute Engine:** VMs should have no external IP when unnecessary, attach a least-privilege runtime service account, and check shielded settings and routes/egress.
- **Cloud SQL private IP:** requires Private Service Access/Private Service Connect or a supported connection; a custom VPC alone is not enough to connect to Cloud SQL.

The landing zone MVP is only a **starting point**, not a certification that any application can be safely deployed without additional design.

## 8. Project-Scoped Billing Budget and Cost Alerts

### 8.1. Distinguishing Budget from Spending Cap

An **alerts-only budget** is used to monitor and send notifications when `CURRENT_SPEND` or `FORECASTED_SPEND` thresholds are reached. It **does not automatically shut down VMs, block APIs, disable billing, or guarantee costs stay below the limit**. Usage data and notifications have latency.

Google Cloud also offers **spend cap budgets** for certain supported services/conditions. That is a **different mechanism** and you must not assume the `google_billing_budget` alerts-only configuration below creates a hard cap. If a service supports it, read the specific spend cap conditions before using it.

### 8.2. Identifying the Billing Account and Project Number

`foundation/budget.tf`:

~~~hcl
data "google_billing_account" "selected" {
  billing_account = var.billing_account_id
  lookup_projects = false
}
~~~

`google_project.sandbox.project_id` is a string ID; **`budget_filter.projects`** requires a resource name using the **numeric project number**. Terraform exposes `google_project.sandbox.number`.

### 8.3. Monthly Budget with 50%, 90%, 100%, and Forecast Alerts

~~~hcl
resource "google_billing_budget" "sandbox" {
  billing_account = data.google_billing_account.selected.id
  display_name    = "orders-sandbox-monthly-budget"

  budget_filter {
    projects        = [format("projects/%s", google_project.sandbox.number)]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = var.monthly_budget_units
    }
  }

  threshold_rules {
    threshold_percent = 0.50
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 0.90
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.00
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.00
    spend_basis       = "FORECASTED_SPEND"
  }
}
~~~

Assuming the account uses USD and sets `monthly_budget_units = "50"`, the thresholds mean:

| Rule | Equivalent Level | Meaning |
| --- | --- | --- |
| `CURRENT_SPEND = 0.50` | 25 USD | Actual spend has reached roughly 50% of the budget |
| `CURRENT_SPEND = 0.90` | 45 USD | Running resources should be reviewed |
| `CURRENT_SPEND = 1.00` | 50 USD | Budget threshold reached/met, **does not automatically block** usage |
| `FORECASTED_SPEND = 1.00` | Forecasted to reach 50 USD in period | Early warning based on forecast; not the final invoice |

The `MONTH` period is one calendar month **based on Cloud Billing time boundaries**, not customized per user's timezone. Reporting latency means that by the time an alert arrives, actual spend may already be higher.

### 8.4. Who Receives Notifications?

Without customizing `all_updates_rule`, an alerts-only budget defaults to emailing the default Billing account IAM recipients. To notify **product owners or FinOps** who do not have Billing Admin permissions, configure an authorized Cloud Monitoring notification channel or Pub/Sub programmatic notifications. Pub/Sub notifications follow an update schedule and are not instantaneous real-time webhooks.

If you only need to monitor a single project, project-level recipient options exist depending on permissions and configuration; not everyone with the Viewer role in the project receives notifications by default.

**Do not automatically disable Billing at 100%** in this lab. Disabling Billing can disrupt applications and have data/service consequences, while notifications may be delayed. Cost-control automation requires safe action selection, proper permissions, idempotency, testing, and a dedicated runbook.

### 8.5. Handling Unexpected Costs

When spend is forecasted to exceed the budget:

1. Check **Billing Reports**, selecting the right billing account and project.
2. Group by service/SKU/region to locate the source of the increase.
3. Verify recently deployed resources, load tests, egress traffic, logs, and storage.
4. You can reduce min instances, stop test environments, or delete unintended resources **via an approved change**.
5. Record the owner and investigation findings; do not raise the budget just to hide alerts.

A budget does not replace **quotas**, **org policies**, autoscaling limits, or resource alerts. Those layers must be designed together.

## 9. Outputs for Landing Zone Handover

`foundation/outputs.tf`:

~~~hcl
output "folder_name" {
  value = google_folder.sandbox.name
}

output "project_id" {
  value = google_project.sandbox.project_id
}

output "project_number" {
  value = google_project.sandbox.number
}

output "vpc_self_link" {
  value = google_compute_network.orders.self_link
}

output "subnet_self_link" {
  value = google_compute_subnetwork.orders_app.self_link
}

output "runtime_service_account" {
  value = google_service_account.orders_runtime.email
}

output "budget_resource_name" {
  value = google_billing_budget.sandbox.name
}
~~~

Outputs report the exact provisioned resources so application teams can obtain the project, subnet, and service account. Do not put access tokens, private keys, database passwords, or sensitive financial details into outputs.

## 10. Declaring Sandbox Values

`environments/sandbox.tfvars`:

~~~hcl
organization_id        = "123456789012"
bootstrap_project_id   = "org-bootstrap-123"
billing_account_id     = "000000-000000-000000"
lab_project_id         = "orders-sandbox-12345"

region                 = "asia-southeast1"
subnet_cidr            = "10.42.0.0/24"

observer_group_email   = "lab-observers@example.com"
network_group_email    = "lab-network@example.com"

budget_currency        = "USD"
monthly_budget_units   = "50"
~~~

All IDs, emails, and amounts in the example are **placeholders**. In a real project, confirm the organization ID, billing account, CIDR, IAM groups, and globally unique project ID. Do not commit credentials into `tfvars`. If your organization treats the billing account ID as sensitive, store variables in a controlled configuration management system.

## 11. Phased Execution

### Phase A — Prepare Permissions and Backend

1. Confirm the executor has permissions on the **organization**, **folder**, **billing account**, and **state bucket**.
2. Enable required APIs on the bootstrap project.
3. Read the effective Organization Policy of the parent folder; prepare to restrict the default network.
4. Verify the Terraform provider version and GCS backend; do not arbitrarily create local state instead of the production backend.
5. Ensure permissions are scoped per operation, without bundling all permissions into the runtime service account.

### Phase B — Initialize and Validate Code

From the `foundation/` directory:

~~~bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file="../environments/sandbox.tfvars" -out="sandbox.tfplan"
terraform show "sandbox.tfplan"
~~~

During the plan review step, verify:

- The folder is created under the correct organization.
- The policy is enforced on the right folder before the project/Compute Engine API creates a default network.
- The project has the billing account, labels, and `deletion_policy=PREVENT`.
- IAM members are **real Google Groups** with the right roles; the runtime SA does not have Owner.
- The VPC uses custom mode, the subnet CIDR does not overlap, and the firewall is not broadly open to the Internet.
- The budget filter contains only the **numeric number** of the sandbox project; the currency matches the billing account.
- There are no unexpected destroy or replace actions.

**Layered deployment:** to give policies time to propagate, organizations should apply the folder/policy in a separate bootstrap stage, verify the effective policy, and then create the project and remaining resources. Do not use `-target` as a routine organizational substitute for clean state/module structure.

### Phase C — Approved Apply

After a reviewer has inspected the same plan file:

~~~bash
terraform apply "sandbox.tfplan"
~~~

**Only run once permissions and cost approval are granted.** After apply, run:

~~~bash
terraform output
terraform state list
terraform plan -var-file="../environments/sandbox.tfvars"
~~~

If the subsequent plan reports unexpected changes, investigate provider defaults, policy propagation, manual edits, or resource drift. Do not automatically run a second apply if there are unreviewed IAM/billing/destroy changes.

## 12. Verifying Results via Cloud Console and gcloud

### 12.1. Resource Hierarchy and Project

~~~bash
gcloud projects describe orders-sandbox-12345 \
  --format="json(projectId,projectNumber,name,parent,labels)"
~~~

Verify the project sits in the right folder and has the expected labels. Billing linkage should also be checked in **Cloud Billing → My projects** or via the Billing API with an authorized principal; describing the project does not prove the budget policy.

### 12.2. APIs, Network, and Subnet

~~~bash
gcloud services list \
  --enabled \
  --project=orders-sandbox-12345

gcloud compute networks describe orders-vpc \
  --project=orders-sandbox-12345

gcloud compute networks subnets describe orders-app \
  --project=orders-sandbox-12345 \
  --region=asia-southeast1

gcloud compute firewall-rules list \
  --project=orders-sandbox-12345
~~~

Verify the network is in custom mode, the subnet uses `10.42.0.0/24`, `privateIpGoogleAccess` is enabled, and only firewall rules within the designed scope exist. If a `default` VPC appears, **do not simply delete it and declare the guardrail passed**: verify the effective `compute.skipDefaultNetworkCreation` policy and the API/project creation lifecycle before remediating drift.

### 12.3. IAM

~~~bash
gcloud projects get-iam-policy orders-sandbox-12345 \
  --format=json
~~~

Cross-check the expected bindings. Verify `lab-observers` only has `roles/logging.viewer`, `lab-network` only has `roles/compute.networkViewer` from the lab module (other bindings from the organization or administrators may exist), and `orders-runtime` is not granted Editor/Owner.

Use **IAM Policy Troubleshooter** when you need to evaluate effective permissions across inherited policies, deny policies, IAM Conditions, and other layers. A binding present in the project policy does not prove a principal holds every permission under the organization.

### 12.4. Billing Budget

Open **Billing → Budgets & alerts**, select the right billing account and the `orders-sandbox-monthly-budget` budget. Verify:

- The scope is **exclusively** the numeric project ID created.
- The monthly period, currency, and amount are correct.
- The 50%, 90%, 100% actual and 100% forecast levels are present.
- Alert recipients or Monitoring/Pub/Sub channels are correct.
- There is no expectation of automatic service shutdown if the lesson only uses an alerts-only budget.

There is no need to generate real spend up to 100% just to test the alert. Verify how the configuration displays and guide the product owner on receiving notifications; to rehearse automation, use synthetic events or a dedicated test channel without disrupting production workloads.

## 13. Positive and Negative Test Matrix

| Test | Condition | Action | Expected Result |
| --- | --- | --- | --- |
| HIER-01 | Correct organization | Describe project/folder | Project belongs to sandbox folder |
| POLICY-01 | Policy propagated | Check effective constraint | `skipDefaultNetworkCreation` is enforced |
| VPC-01 | Compute API enabled | Describe `orders-vpc` | Custom mode, no auto subnets |
| VPC-02 | Subnet created | Describe subnet | Region, CIDR, Private Google Access match |
| FW-01 | No workload yet | Review firewall rules | No broad public SSH/RDP |
| FW-02 | If a test VM with tag `lab-app` is added | TCP `8080` from allowed subnet | Allowed **if app listens** and routes/other policies permit |
| FW-03 | Equivalent test VM outside allowed range | TCP `8080` | Blocked unless another rule widens access |
| IAM-01 | Runtime SA | Review project IAM | No Owner/Editor |
| IAM-02 | Observer group | Check logging viewer role | Reads appropriate logs only, cannot edit network |
| IAM-03 | Network group | Check network viewer role | Views VPC but cannot edit firewall |
| BUDGET-01 | Correct billing account | Check budget filter | Single project and right amount/currency |
| BUDGET-02 | Forecast threshold present | Check threshold rules | Includes 100% forecast and 50/90/100% actual |
| STATE-01 | Remote backend configured | Terraform plan/re-init | No unintended local/scattered state created |
| DRIFT-01 | After apply | Run plan | No unexpected changes |

**Result limitations:** because the MVP has no VMs yet, `FW-02` and `FW-03` are extension exercises rather than already PASSed. The presence of a rule does not prove traffic flows properly. If running live tests, use a small VM without a public IP in a staging project, schedule cleanup, and measure additional costs; never open SSH from `0.0.0.0/0`.

## 14. Monitoring and FinOps After Handover

### 14.1. Evidence to Retain

An acceptance report may contain:

~~~json
{
  "environment": "sandbox",
  "projectId": "orders-sandbox-12345",
  "network": "orders-vpc",
  "subnet": "orders-app",
  "subnetCidr": "10.42.0.0/24",
  "defaultNetworkPolicy": "enforced",
  "runtimeServiceAccount": "orders-runtime@orders-sandbox-12345.iam.gserviceaccount.com",
  "monthlyBudget": {
    "currency": "USD",
    "units": 50,
    "actualThresholds": [0.50, 0.90, 1.00],
    "forecastThreshold": 1.00
  },
  "deployment": "terraform",
  "status": "reviewed"
}
~~~

This is an **illustrative report format**, not the actual result of the learner's environment. Only fill in `enforced` and `reviewed` after verification. Never include service account keys, access tokens, passwords, or state files in acceptance reports.

### 14.2. Incident Workflow When Spend Increases

- Product owner/FinOps receives the alert and checks Billing Reports by service, SKU, and region.
- Infrastructure team inspects newly created resources, log volume, egress, and utilization.
- Security team checks the principal that created the resources and Cloud Audit Logs.
- If the lab needs to be paused, decide to stop resources **by workload type**, rather than broadly disabling the Billing account.
- After resolution, update the budget/alert thresholds based on actual usage and assign an accountable owner.

You can extend this with **Cloud Billing export to BigQuery**, daily/weekly reports, labels by owner/cost center, and unusual spend alerting. Do not calculate a project's individual cost by summing everything across the billing account without properly filtering by project/credits.

### 14.3. Operational SLIs/SLOs

Before workloads exist, there is no application latency SLO. Instead, track foundational indicators:

- **Compliance:** % of projects with labels, budget, service identity, and correct folder.
- **Security:** count of over-privileged IAM bindings; count of policy-violating default VPCs.
- **Network hygiene:** count of overly broad ingress firewall rules.
- **Cost governance:** % of projects with a budget and alert owner; alert response time.
- **Automation quality:** rate of Terraform plans showing drift or unapproved destructive changes.

Once the Java application is deployed, add logs/metrics/traces, availability, p95 latency, and business error budgets.

## 15. Cleanup and Data Protection at Lab End

**Do not run `terraform destroy` immediately on a project unless you are certain it is the sandbox.** Before destroying:

1. Confirm the exact `lab_project_id`, folder, billing account, and state backend; verify the state file only contains lab resources.
2. Ensure no data, secrets, VMs, disks, IPs, databases, backups, or workloads still need to be retained.
3. Run `terraform plan -destroy -var-file="../environments/sandbox.tfvars"`; review the complete impact list.
4. Because `google_project.sandbox.deletion_policy = "PREVENT"`, Terraform will block deleting the project. To delete the **lab project**, obtain separate change approval to switch the policy to `DELETE` (or handle the project per organization policy), then re-review the destroy plan.
5. If you only want Terraform to stop managing the project **without deleting the project**, consider the `ABANDON` mechanism with approval, rather than conflating it with deleting resources.
6. Wait for resources to finish deleting/recovering and check remaining charges; backup retention, logging, and billing export may continue incurring fees or retaining data.
7. Keep audit evidence and close the budget if no tracked project remains. Do not delete a bootstrap state bucket shared with other environments.

Destruction order may be constrained by IAM/policies, project liens, and deletion protection. If the command returns an error, do not remove organization protections just to delete faster; escalate to an authorized owner to handle.

## 16. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Folder creation returns `403` | Missing Folder Creator on parent | Grant role at the right scope or use an admin-provisioned folder |
| Cannot create project | Missing Project Creator, duplicate ID, or policy block | Check organization/folder, project ID, and effective policy |
| Billing link fails | Missing Billing User or project billing management permission | Check Billing IAM and billing account status |
| `google_org_policy_policy` denied | Missing Org Policy Admin or API not enabled | Admin applies policy beforehand, verify inheritance |
| Project still has `default` VPC | Constraint not yet effective when project/API created network | Evaluate policy propagation and project creation history, remediate drift intentionally |
| VPC/subnet error | Compute API not enabled, overlapping CIDR, or quota | Check service enablement, region, and IP planning |
| Runtime SA appears overly privileged | Inherited IAM role at folder/organization level | Use Policy Troubleshooter, review inherited bindings |
| Firewall `allow` exists but TCP fails | No VM/tag/app listener yet, route or another rule blocking | Do not treat policy config check as an integration test |
| `google_billing_budget` returns `403` with user ADC | Missing `billing_project`, quota override, or Billing Costs Manager role | Check provider config, `serviceusage.services.use`, and billing IAM |
| Budget created but expected emails not sent | Recipient not in default group / missing Monitoring channel | Check notification rules and billing account recipients |
| Spend continues rising past 100% | Alerts-only budget does not stop services, reporting delay | Monitor Billing Reports; use other appropriate controls |
| `terraform init` fails | Backend bucket does not exist yet or missing IAM | Fix bootstrap state bucket/credentials, do not leave state scattered |
| `terraform destroy` blocked | Project deletion policy `PREVENT` | This is the expected guardrail; request approval then handle the lab |
| Plan shows unexpected IAM changes | Another state manages IAM policy or drift exists | Review authoritative/member resources, do not apply without inspection |

## 17. Project Acceptance Checklist

- [ ] Organization, folder, billing account, bootstrap project, and GCS state bucket exist.
- [ ] Terraform execution identity has only the permissions needed for bootstrap/foundation; no long-lived JSON keys used.
- [ ] Sandbox folder created under the right parent; project ID is unique and has owner/cost area labels.
- [ ] Organization Policy blocking default network creation verified as effective before project provisioning.
- [ ] Project linked to the right billing account and protected from accidental Terraform deletion via `deletion_policy=PREVENT`.
- [ ] Service APIs enabled; unnecessary services are not enabled.
- [ ] Dedicated `orders-runtime` service account created, without Owner/Editor.
- [ ] Observer and network groups receive least-privilege roles, without extraneous IAM or Billing permissions.
- [ ] Custom-mode VPC and subnet match region/CIDR without overlap.
- [ ] Private Google Access enabled on the subnet and understood not to be IAM.
- [ ] No public SSH/RDP firewall ingress; `8080` rule applies only to tagged lab VMs.
- [ ] Budget scoped to **numeric project number**, right currency, monthly period.
- [ ] 50/90/100% actual and 100% forecast thresholds verified.
- [ ] Budget owner understands an **alert budget is not a spending cap**.
- [ ] Terraform plan reviewed; post-apply plan shows no unexpected drift.
- [ ] Handover details, owner, alert recipients, and incident runbook saved.
- [ ] Decommission process with approval and bootstrap state protection in place.

## References

- [Google Cloud landing zones](https://docs.cloud.google.com/architecture/landing-zones) — foundational components and architectural options.
- [Google Cloud resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy) — organization, folders, projects, and policy inheritance.
- [Organization Policy: Restrict resource configurations](https://docs.cloud.google.com/resource-manager/docs/organization-policy/overview) — constraints and effective policies.
- [Compute Engine VPC networks](https://docs.cloud.google.com/vpc/docs/vpc) — custom/auto-mode VPC, routes, firewall behavior.
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access) — conditions for accessing Google APIs from VMs without external IPs.
- [Cloud Billing: Create budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — alerts-only budget, scope, notification delays, and separate spend caps.
- [Cloud Billing: Programmatic budget notifications](https://docs.cloud.google.com/billing/docs/how-to/notify) — Pub/Sub notifications and cost automation integration.
- [Terraform google_project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project) — project, folder, billing, labels, and deletion policy.
- [Terraform google_org_policy_policy](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy) — boolean policy for folder/project.
- [Terraform google_project_iam_member](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_iam) — non-authoritative IAM bindings.
- [Terraform google_compute_network](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network) — custom VPC.
- [Terraform google_compute_subnetwork](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork) — CIDR and Private Google Access.
- [Terraform google_compute_firewall](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall) — source ranges, target tags, and ingress/egress.
- [Terraform google_billing_budget](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/billing_budget) — monthly budget filter, numeric project number, and alert thresholds.
- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs) — remote state, locking, and backend authentication.

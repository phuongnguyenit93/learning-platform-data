# Hands-On: Deploying a Minimal Landing Zone as Code

In the `CLOUD_PROVIDERS_GCP` module, you explore Google Cloud from organizations, projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Before placing workloads onto those services, an organization needs a shared foundation to manage identities, separate environments, control networking, retain audit trails, and manage costs.

A landing zone is a cloud foundation designed so workloads can be deployed and operated under consistent rules. This hands-on exercise builds a minimal GCP landing zone with Terraform: organization and folders, foundational projects, Shared VPC, required APIs, several organization policy guardrails, and centralized audit log storage. You will deploy in layers to understand dependency order and change control.

## 1. Landing Zone Goals and Scope

A landing zone is more than a VPC or a sample project. It combines identity, resource hierarchy, networking, and security controls; monitoring/logging, backups, cost management, and hybrid connectivity can be added as needed. The design should start small enough for the first workload while remaining modular enough to scale.

This lab creates an illustrative foundation consisting of:

- An organization resource already set up through Google Workspace or Cloud Identity.
- Folders separating bootstrap, shared infrastructure, production, and non-production.
- Separate projects for shared networking, audit log storage, and each environment's workloads.
- A Shared VPC host project providing subnets to service projects.
- Organization policies preventing creation of default networks and new service account keys.
- An organization-level log sink routing audit logs to centralized storage.
- Terraform state stored in Cloud Storage with versioning and dedicated access control.

Target diagram:

~~~mermaid
flowchart TB
  ORG[Google Cloud Organization]
  ORG --> BOOT[bootstrap folder]
  ORG --> SHARED[shared infrastructure folder]
  ORG --> NONPROD[non-production folder]
  ORG --> PROD[production folder]
  BOOT --> STATE[Terraform state / CI identity]
  SHARED --> NET[network-host project]
  SHARED --> LOG[central-logs project]
  NONPROD --> DEV[app-dev project]
  PROD --> APP[app-prod project]
  NET --> VPC[Shared VPC + subnets]
  VPC --> DEV
  VPC --> APP
  ORG --> POLICY[Organization policies]
  ORG --> SINK[Organization audit-log sink]
  SINK --> LOG
~~~

This is a small learning design. In a large enterprise, you may need separate Shared VPCs for production and non-production, multiple network projects, a dedicated security folder, VPC Service Controls, Cloud NAT, Cloud DNS, hybrid connectivity, and additional policies. No single folder or network layout fits every enterprise.

## 2. Preparing Before Running Terraform

### 2.1. Prerequisite Resources

Terraform cannot create an organization resource or billing account from a regular project on its own. Before running the foundation stack, you need:

1. A Google Cloud organization linked to Google Workspace or Cloud Identity.
2. An active billing account.
3. Organization ID and billing account ID.
4. A bootstrap project to enable APIs, grant permissions for Terraform, and store Terraform state.
5. A Terraform execution identity with permissions to create folders/projects, configure IAM, organization policies, Shared VPC, and log sinks.

The bootstrap project and state bucket must exist before the GCS backend can be initialized. You can create them in a separate bootstrap step using initial administrative procedures, then move the foundation stack onto the remote backend. Never make a state backend depend on the very bucket that state is supposed to create.

### 2.2. Execution Identity Permissions

Grant permissions per resource layer. The roles below are commonly required; exact permissions depend on resources and how you split stacks:

| Task | Commonly Required Role | Scope |
| --- | --- | --- |
| Create folders | `roles/resourcemanager.folderCreator` | Organization or parent folder |
| Create projects | `roles/resourcemanager.projectCreator` | Organization or parent folder |
| Link projects to a billing account | `roles/billing.user` on billing account and project billing management permissions | Billing account/project |
| Manage organization policies | `roles/orgpolicy.policyAdmin` | Managed organization or folder |
| Enable APIs in a project | `roles/serviceusage.serviceUsageAdmin` | Project |
| Manage Shared VPC | `roles/compute.xpnAdmin` and required network admin permissions | Organization/host project |
| Manage VPC/subnets/firewalls | `roles/compute.networkAdmin` | Network host project |
| Create an organization log sink | `roles/logging.configWriter` or equivalent permissions | Organization |
| Grant IAM on resources | Resource-appropriate IAM permissions, e.g., IAM admin role at the exact scope | Organization/folder/project |

Separate broad bootstrap permissions from day-to-day operational permissions. In production, do not use basic roles like Owner, Editor, or Viewer as general deployment permissions. Instead, grant specialized roles or custom roles containing only the permissions the stack needs.

When using short-lived identities via Workload Identity Federation or service account impersonation, apply the earlier Terraform authentication lesson: the CI identity may only impersonate the designated deployment service account; that service account receives foundation management permissions within the approved scope.

### 2.3. Enable APIs Needed for Bootstrap

In the bootstrap project, enable the APIs required by the management workflow. For example:

~~~bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  orgpolicy.googleapis.com \
  serviceusage.googleapis.com \
  logging.googleapis.com \
  --project=BOOTSTRAP_PROJECT_ID
~~~

Some APIs are enabled in target projects when Terraform creates projects and activates services. The Service Usage API must be available so Terraform can manage `google_project_service`.

## 3. Setting Up Terraform Root and Remote State

### 3.1. Directory Layout

Organize code by layers so hierarchy changes do not force editing networking or workloads at the same time:

~~~text
landing-zone/
├── bootstrap/
│   └── state-bucket/          # created once before the foundation stack
├── foundation/
│   ├── versions.tf
│   ├── providers.tf
│   ├── backend.tf
│   ├── variables.tf
│   ├── folders-projects.tf
│   ├── policies.tf
│   ├── networking.tf
│   ├── logging.tf
│   └── outputs.tf
└── environments/
    ├── dev.tfvars
    └── prod.tfvars
~~~

The example below groups core files together for easier learning. In real usage, split into modules by responsibility and keep input/output interfaces clear.

### 3.2. Declaring Provider Versions

`versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}
~~~

`~> 8.0` is an example for Google provider major version 8. Choose a range compatible with the provider version tested by your organization, run `terraform init` to create/update `.terraform.lock.hcl`, and commit the lock file to Git. Never automatically upgrade major versions inside production pipelines.

### 3.3. Declaring Provider and Backend

`providers.tf`:

~~~hcl
provider "google" {
  project = var.bootstrap_project_id
  region  = var.region
}
~~~

The provider uses Application Default Credentials (ADC). On a development machine, log in with user ADC; in CI/CD, prefer Workload Identity Federation or a service account attached to a runner on Google Cloud. Avoid putting service account JSON keys into Terraform code or long-lived environment variables.

`backend.tf`:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "REPLACE_WITH_PRECREATED_TFSTATE_BUCKET"
    prefix = "landing-zone/foundation"
  }
}
~~~

Replace `bucket` with the name of the pre-created bootstrap bucket. The GCS backend stores state centrally and supports state locking. Enable Object Versioning on the bucket so prior state versions can be recovered if mistakes occur. Use Uniform Bucket-Level Access, Public Access Prevention, and least-privilege IAM; only authorized deployment identities and operators should have read/write access to state.

The backend initializes during `terraform init`, before Terraform executes provider resources. Therefore, state bucket access permissions must be configured separately and verified before running `plan`. If the backend must impersonate another service account, configure `impersonate_service_account` for the GCS backend or the corresponding environment variables; backend access is not automatically granted simply because the provider has permissions to create resources.

### 3.4. Declaring Variables

`variables.tf`:

~~~hcl
variable "organization_id" {
  description = "Numeric ID of the Google Cloud organization."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account ID used for new projects."
  type        = string
}

variable "bootstrap_project_id" {
  description = "Existing project used as the provider's default project."
  type        = string
}

variable "network_project_id" {
  description = "Globally unique project ID for the Shared VPC host."
  type        = string
}

variable "logs_project_id" {
  description = "Globally unique project ID for centralized logs."
  type        = string
}

variable "dev_project_id" {
  description = "Globally unique project ID for the development workload."
  type        = string
}

variable "prod_project_id" {
  description = "Globally unique project ID for the production workload."
  type        = string
}

variable "region" {
  description = "Primary region for the sample network."
  type        = string
  default     = "asia-southeast1"
}

variable "dev_subnet_cidr" {
  type    = string
  default = "10.40.0.0/20"
}

variable "prod_subnet_cidr" {
  type    = string
  default = "10.50.0.0/20"
}

variable "developer_group_email" {
  description = "Google Group for application developers."
  type        = string
}

variable "prod_operator_group_email" {
  description = "Google Group allowed to use production subnets."
  type        = string
}

variable "log_archive_bucket_name" {
  description = "Globally unique name for the audit-log archive bucket."
  type        = string
}
~~~

Project IDs and bucket names must be unique per Google Cloud naming rules. Never use example values in real environments if another organization already claimed them. Manage environment values in `.tfvars` or pipeline variables; never put credentials in `.tfvars`.

## 4. Creating the Resource Hierarchy and Projects

### 4.1. Creating Folders by Environment and Function

`folders-projects.tf`:

~~~hcl
resource "google_folder" "bootstrap" {
  display_name = "Bootstrap"
  parent       = format("organizations/%s", var.organization_id)
}

resource "google_folder" "shared" {
  display_name = "Shared Infrastructure"
  parent       = format("organizations/%s", var.organization_id)
}

resource "google_folder" "nonprod" {
  display_name = "Non-Production"
  parent       = format("organizations/%s", var.organization_id)
}

resource "google_folder" "prod" {
  display_name = "Production"
  parent       = format("organizations/%s", var.organization_id)
}
~~~

The bootstrap project already exists before the foundation stack and serves as the provider's default project. The Bootstrap folder in this example is a placement point for future foundational resources; if the bootstrap project currently sits elsewhere in the hierarchy, plan a separate migration or import the existing folder/project. Do not move active projects solely to make the hierarchy match the diagram.

Folders are inheritance points for IAM and organization policies. For instance, the network operations team can manage resources inside Shared Infrastructure; application teams receive permissions on their corresponding environment folder. Separating by environment lets you apply different policies and permissions to production and non-production.

There is no need to create many folder layers from day one. Only add folders when there is an administrative, security, cost, or lifecycle boundary to express. Use consistent names and avoid tying folders to individual names or employee locations.

### 4.2. Creating Foundation and Workload Projects

~~~hcl
resource "google_project" "network_host" {
  name            = "Shared Network Host"
  project_id      = var.network_project_id
  folder_id       = google_folder.shared.name
  billing_account = var.billing_account_id
}

resource "google_project" "central_logs" {
  name            = "Central Logs"
  project_id      = var.logs_project_id
  folder_id       = google_folder.shared.name
  billing_account = var.billing_account_id
}

resource "google_project" "app_dev" {
  name            = "Application Development"
  project_id      = var.dev_project_id
  folder_id       = google_folder.nonprod.name
  billing_account = var.billing_account_id
}

resource "google_project" "app_prod" {
  name            = "Application Production"
  project_id      = var.prod_project_id
  folder_id       = google_folder.prod.name
  billing_account = var.billing_account_id
}
~~~

Each project is the management unit for APIs, IAM, billing, and service resources. Separating network host, central logs, and workload projects limits permissions and tracks costs by purpose. Billing accounts attach at the project level; folders do not act as billing accounts themselves.

If a project already exists, do not recreate it with a different ID just to put it into Terraform. Assess its current state and use `terraform import` or `import` blocks to bring existing resources into state. Importing requires verifying the exact resource address, project ID, and configuration before applying.

### 4.3. Enabling APIs per Project

~~~hcl
resource "google_project_service" "network_host" {
  for_each = toset([
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.network_host.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "central_logs" {
  for_each = toset([
    "storage.googleapis.com",
    "logging.googleapis.com"
  ])

  project            = google_project.central_logs.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "app_dev" {
  for_each = toset([
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.app_dev.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "app_prod" {
  for_each = toset([
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.app_prod.project_id
  service            = each.value
  disable_on_destroy = false
}
~~~

Enable only APIs the project needs. `disable_on_destroy = false` prevents Terraform from automatically disabling an API when the service resource is removed from configuration. This helps because APIs may be used by resources outside the current state's scope. Manage APIs as part of the project baseline and review changes before applying.

### 4.4. Granting Group Permissions by Folder

Example granting view-only permissions to the development group on the non-production folder:

~~~hcl
resource "google_folder_iam_member" "nonprod_developers_viewer" {
  folder = google_folder.nonprod.name
  role   = "roles/viewer"
  member = format("group:%s", var.developer_group_email)
}
~~~

`google_folder_iam_member` adds one member to one role without replacing the entire policy. Prefer narrowly scoped IAM `member` or `binding` resources. Avoid authoritative IAM `policy` resources because they can replace the entire existing policy and accidentally strip other bindings.

The Viewer role in this example grants read access only. When a team needs to deploy workloads, grant additional specific roles on the managed project or resource, with IAM conditions where appropriate. Never grant Editor across an entire folder just to make a pipeline run.

## 5. Applying Organization Policy Guardrails

Organization policies set consistent configuration constraints across all descendants of an organization or folder. This lab applies two foundational guardrails:

1. Do not create a default VPC network when new projects are created.
2. Do not create user-managed service account keys.

`policies.tf`:

~~~hcl
resource "google_org_policy_policy" "skip_default_network" {
  name   = format("organizations/%s/policies/compute.skipDefaultNetworkCreation", var.organization_id)
  parent = format("organizations/%s", var.organization_id)

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}

resource "google_org_policy_policy" "disable_service_account_keys" {
  name   = format("organizations/%s/policies/iam.managed.disableServiceAccountKeyCreation", var.organization_id)
  parent = format("organizations/%s", var.organization_id)

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
~~~

`google_org_policy_policy` uses Organization Policy API v2. Policy names include the parent resource and constraint. Policies are inherited down to folders and projects; a lower-level policy can alter the effective result according to Organization Policy inheritance rules.

The service account key guardrail is appropriate once the organization uses Workload Identity Federation, service account impersonation, or service accounts attached to compute resources. Before enforcing broadly, verify whether existing pipelines and workloads still depend on JSON keys. Blocking key creation does not automatically migrate legacy systems already using keys.

Organization policies can cause certain resource creation actions to fail. For example, a constraint blocking service account creation can prevent some services from auto-creating default service accounts when enabling APIs. Therefore, this lab does not enable the constraint blocking service account creation; evaluate impacts and deployment ordering separately before enforcing that constraint.

In production, review each guardrail with the security team, check inheritance, and establish a time-bound exception process. Never use policies to replace IAM; policies restrict resource configuration, whereas IAM defines who is permitted to perform actions.

## 6. Creating a Shared VPC for Workload Projects

Shared VPC lets the network team manage networks in a host project while workloads live in service projects. This separates network administration permissions from application deployment permissions.

### 6.1. Enabling the Shared VPC Host Project

`networking.tf`:

~~~hcl
resource "google_compute_shared_vpc_host_project" "host" {
  project = google_project.network_host.project_id

  depends_on = [
    google_project_service.network_host["compute.googleapis.com"]
  ]
}

resource "google_compute_network" "shared" {
  project                 = google_project.network_host.project_id
  name                    = "shared-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"

  depends_on = [
    google_compute_shared_vpc_host_project.host
  ]
}
~~~

`auto_create_subnetworks = false` creates a custom-mode VPC, allowing you to control CIDRs per region. The host project requires the Compute Engine API and appropriate Shared VPC administration permissions.

### 6.2. Creating Subnets by Environment

~~~hcl
resource "google_compute_subnetwork" "dev" {
  project                  = google_project.network_host.project_id
  name                     = format("dev-%s", var.region)
  region                   = var.region
  network                  = google_compute_network.shared.id
  ip_cidr_range            = var.dev_subnet_cidr
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "prod" {
  project                  = google_project.network_host.project_id
  name                     = format("prod-%s", var.region)
  region                   = var.region
  network                  = google_compute_network.shared.id
  ip_cidr_range            = var.prod_subnet_cidr
  private_ip_google_access = true
}
~~~

CIDRs must not overlap with on-premises networks, VPNs, VPC peering, or other VPCs that may connect later. `private_ip_google_access` lets VMs without external IPs reach Google APIs and services over an appropriate private path. Depending on requirements, you can add Cloud NAT, Private Service Access, firewall rules, Cloud DNS, and hybrid connectivity in subsequent steps.

### 6.3. Attaching Service Projects to the Host Project

~~~hcl
resource "google_compute_shared_vpc_service_project" "dev" {
  host_project    = google_compute_shared_vpc_host_project.host.project
  service_project = google_project.app_dev.project_id

  depends_on = [
    google_project_service.app_dev["compute.googleapis.com"],
    google_compute_subnetwork.dev
  ]
}

resource "google_compute_shared_vpc_service_project" "prod" {
  host_project    = google_compute_shared_vpc_host_project.host.project
  service_project = google_project.app_prod.project_id

  depends_on = [
    google_project_service.app_prod["compute.googleapis.com"],
    google_compute_subnetwork.prod
  ]
}
~~~

Associating a service project with a host project does not automatically grant subnet usage permissions to every identity. Grant `roles/compute.networkUser` on the appropriate subnet or network scope to service accounts and deployment groups that need to create resources in the Shared VPC. Keep this permission on the exact subnet to avoid a non-production workload accidentally using a production network.

Example granting Network User separately per subnet to the corresponding deployment group:

~~~hcl
resource "google_compute_subnetwork_iam_member" "dev_network_users" {
  project    = google_compute_subnetwork.dev.project
  region     = google_compute_subnetwork.dev.region
  subnetwork = google_compute_subnetwork.dev.name
  role       = "roles/compute.networkUser"
  member     = format("group:%s", var.developer_group_email)
}

resource "google_compute_subnetwork_iam_member" "prod_network_users" {
  project    = google_compute_subnetwork.prod.project
  region     = google_compute_subnetwork.prod.region
  subnetwork = google_compute_subnetwork.prod.name
  role       = "roles/compute.networkUser"
  member     = format("group:%s", var.prod_operator_group_email)
}
~~~

One Shared VPC with two subnets is a simple learning example. In environments with strict isolation requirements, use separate Shared VPCs for production and non-production, then design firewall policies, routes, and network user permissions separately per host project. Do not share one subnet across all workloads merely because they share a region.

## 7. Centralizing Audit Logs in the Management Project

Audit logs help security and operations teams investigate resource changes, IAM changes, and API activity. An organization-level aggregated sink can collect logs from the organization and child projects, then route them to centralized storage.

### 7.1. Creating the Log Archive Bucket

`logging.tf`:

~~~hcl
resource "google_storage_bucket" "audit_archive" {
  project                     = google_project.central_logs.project_id
  name                        = var.log_archive_bucket_name
  location                    = "ASIA"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  depends_on = [
    google_project_service.central_logs["storage.googleapis.com"]
  ]
}
~~~

This bucket is the archive destination. In real environments, choose `location` based on data residency, retention, and query requirements. Configure retention policies, object lifecycles, access logging, and data deletion workflows matching organizational policy. Do not grant broad read access to application users.

### 7.2. Creating the Organization Log Sink

~~~hcl
resource "google_logging_organization_sink" "audit_archive" {
  name             = "organization-audit-archive"
  org_id           = var.organization_id
  destination      = format("storage.googleapis.com/%s", google_storage_bucket.audit_archive.name)
  include_children = true

  filter = "logName:\"cloudaudit.googleapis.com\""
}
~~~

The sink sets `include_children = true` to capture logs from child projects. The filter restricts ingestion to Cloud Audit Logs. Depending on requirements, you can expand the filter to collect application logs, VPC Flow Logs, or firewall logs; evaluate volume and cost before collecting everything.

### 7.3. Granting Write Access to the Sink Writer Identity

~~~hcl
resource "google_storage_bucket_iam_member" "audit_sink_writer" {
  bucket = google_storage_bucket.audit_archive.name
  role   = "roles/storage.objectCreator"
  member = google_logging_organization_sink.audit_archive.writer_identity
}
~~~

When creating a sink, Cloud Logging assigns a dedicated writer identity. You must grant object creation permission to that identity on the destination bucket; without this binding, the sink can exist yet logs will not be written to the destination. Terraform creates the bucket first, creates the sink to obtain its writer identity, and then grants the corresponding IAM permission.

To support investigations, clearly define who can view archives, who can modify the sink, and who can delete buckets/objects. Sink configuration permissions at the organization scope affect many projects and must be reviewed like security changes.

## 8. Declaring Outputs to Verify Results

`outputs.tf`:

~~~hcl
output "folder_ids" {
  value = {
    bootstrap = google_folder.bootstrap.name
    shared    = google_folder.shared.name
    nonprod   = google_folder.nonprod.name
    prod      = google_folder.prod.name
  }
}

output "project_ids" {
  value = {
    network_host = google_project.network_host.project_id
    central_logs = google_project.central_logs.project_id
    app_dev      = google_project.app_dev.project_id
    app_prod     = google_project.app_prod.project_id
  }
}

output "shared_vpc_network" {
  value = google_compute_network.shared.self_link
}

output "audit_sink_writer_identity" {
  value = google_logging_organization_sink.audit_archive.writer_identity
}
~~~

Outputs help pipelines or operators verify created resources and capture identifiers for subsequent configuration steps. Never put secrets or access tokens into outputs. Project IDs, folder names, and network self-links are not credentials, but should still be handled according to organizational infrastructure information policies.

## 9. Phased Deployment

Do not run one giant `apply` on the first pass. Deploying in layers lets you verify permissions, billing, and policies before creating networks or sinks.

### Step 1: Initialize the Backend

~~~bash
terraform init
~~~

If the GCS backend does not yet exist or the execution identity cannot read/write the bucket, stop at this step and resolve permissions. Never fall back temporarily to local state in a production pipeline without a migration plan and state controls.

### Step 2: Check Environment Variables

Create `environments/dev.tfvars`:

~~~hcl
organization_id          = "123456789012"
billing_account_id       = "000000-000000-000000"
bootstrap_project_id     = "org-bootstrap-123"
network_project_id       = "org-network-host-123"
logs_project_id          = "org-central-logs-123"
dev_project_id           = "org-app-dev-123"
prod_project_id          = "org-app-prod-123"
region                   = "asia-southeast1"
dev_subnet_cidr          = "10.40.0.0/20"
prod_subnet_cidr         = "10.50.0.0/20"
developer_group_email    = "cloud-developers@example.com"
prod_operator_group_email = "cloud-operations@example.com"
log_archive_bucket_name  = "org-audit-archive-123456789012"
~~~

Replace all illustrative values with real IDs and CIDRs approved by the network team. `.tfvars` files contain configuration only—never JSON keys, passwords, or access tokens. If environment IDs are considered sensitive under internal policy, store them in a controlled configuration repository.

### Step 3: Format and Validate

~~~bash
terraform fmt -recursive
terraform validate
~~~

`terraform fmt` standardizes HCL formatting; `terraform validate` checks structure and configuration types after providers have been initialized. Neither command confirms whether the identity holds sufficient IAM permissions or whether organization policies allow creating resources.

### Step 4: Review the Plan

~~~bash
terraform plan \
  -var-file="environments/dev.tfvars" \
  -out="foundation-dev.tfplan"
~~~

Read the plan carefully before applying. Confirm the exact organization, parent folders, project IDs, billing account, CIDRs, log sink destination, and enforced policies. Pay special attention to IAM and organization policy changes because they can affect existing workloads outside the stack.

Plan files can contain sensitive values from state or configuration. Protect plan files like internal infrastructure data; never commit them to Git or upload them to public locations.

### Step 5: Controlled Apply

~~~bash
terraform apply "foundation-dev.tfplan"
~~~

Only apply a plan reviewed and approved per organizational change procedures. For production, use a pipeline with access controls, environment approvals, and a verified execution identity. Never use `-auto-approve` for an initial foundation deployment.

### Step 6: Verify Outputs and State

~~~bash
terraform output folder_ids
terraform output project_ids
terraform output shared_vpc_network
terraform state list
~~~

Cross-check outputs against Resource Manager, IAM, VPC, and Logging in the Console. Terraform state must reside in the remote backend with state locking active and access restricted to required teams.

## 10. Post-Deployment Landing Zone Verification

Use the following checklist to verify each layer:

| Layer | Check | Expected Result |
| --- | --- | --- |
| Hierarchy | Inspect organization and folders | Bootstrap, Shared Infrastructure, Non-Production, and Production appear under the right parent. |
| Projects | Inspect project list and billing | Network host, central logs, app dev, and app prod sit in the right folders and link to the billing account. |
| APIs | Inspect enabled APIs per project | Only required APIs are enabled; Compute Engine API is ready for Shared VPC. |
| Organization policies | Inspect policy inheritance | Default network creation and service account key creation are restricted per configured policies. |
| Shared VPC | Inspect host/service project associations | App dev and app prod are attached to the right host project. |
| Subnets | Check regions and CIDRs | Subnets do not overlap and belong to the right VPC. |
| Network IAM | Check `roles/compute.networkUser` | Only authorized deployment/workload identities can use subnets. |
| Logging | Check organization sink and destination | Sink includes children; writer identity has permission to write to the bucket. |
| Terraform state | Run `terraform plan` again | No unexpected changes appear after a successful deployment. |

A second `terraform plan` showing no unexpected changes is a good signal that configuration and state are synchronized. However, still inspect out-of-band configuration, audit logs, and IAM permissions to detect manual changes or drift.

## 11. Operating and Scaling the Landing Zone

A landing zone is a living foundation alongside workloads. Once created, maintain these practices:

- **Keep bootstrap separate:** manage the state bucket, CI identities, and pipelines in a bootstrap stack with a controlled lifecycle.
- **Split state by layer:** hierarchy/policies, networking, logging, and workloads can have separate states to reduce blast radius and required permissions.
- **Protect production:** require approvals for apply, review plans, and restrict who can modify folders, IAM, org policies, or networks.
- **Manage drift:** run scheduled plans, investigate out-of-band changes, and import approved resources into IaC management.
- **Expand logging:** add retention, Log Analytics/BigQuery, alerts, and incident handling workflows; ensure log sinks are not tampered with.
- **Manage costs:** apply labels and budgets by project, environment, and owner; inspect billing exports to analyze workload costs.
- **Expand networking:** add Cloud NAT, Cloud DNS, firewall policies, Private Service Connect, or hybrid connectivity as real requirements arise.
- **Isolate environments:** if production and non-production have differing security requirements, consider separate host projects and Shared VPCs rather than only separate subnets.
- **Review guardrails:** test organization policies in a sandbox or test folder before enforcing broadly across the organization.

If a landing zone spans many projects and teams, consider Google Cloud Foundation Fabric or the Enterprise Foundations Blueprint. Those solutions provide broader modules and reference architectures for enterprises; this lab serves as a starting point to understand the core building blocks.

## 12. Common Issues and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Folder creation gets 403 | Terraform identity lacks Folder Creator on organization or parent folder. | Grant permission at the right scope and verify the active principal running Terraform. |
| Project creation denied | Missing Project Creator or project ID already exists. | Check IAM, ID uniqueness, and existing project status. |
| Cannot link billing | Missing permissions on billing account or project. | Check Billing User and Project Billing Manager permissions. |
| Cannot enable API | Service Usage API not enabled or identity lacks Service Usage Admin. | Enable required APIs in bootstrap and grant role on target project. |
| Blocked by organization policy | Inherited policy or another constraint blocks the operation. | Inspect policies at organization/folder/project and evaluate impact before overriding. |
| Shared VPC association error | Compute API not enabled or missing Shared VPC Admin. | Enable API in both host/service projects and grant permissions at the right scope. |
| Workload cannot use subnet | Service project attached, but principal lacks Network User. | Grant `roles/compute.networkUser` on subnet/host project with least privilege. |
| Log sink not writing to bucket | Writer identity was not granted object creation permissions. | Grant `roles/storage.objectCreator` to the writer identity on the destination bucket. |
| `terraform init` 403 error | Backend identity lacks access to the GCS state bucket. | Check ADC/impersonation and bucket IAM; backend permissions are independent of the resource provider. |
| Terraform wants to replace project or folder | Immutable attribute changed or configuration mismatches existing resource. | Review plan, import, or perform controlled migration; never apply without understanding impact. |

Never resolve permission errors by temporarily granting Owner or Editor and forgetting to revoke it. Identify the missing permission, grant the narrowest role for the required duration, and record the IAM change.

## 13. Minimal Landing Zone Completion Checklist

- [ ] Organization resource and billing account already exist.
- [ ] Bootstrap project, remote state bucket, and Terraform execution identity are ready.
- [ ] Terraform uses pinned provider versions and ADC/WIF instead of long-lived service account keys.
- [ ] Folder hierarchy separates bootstrap, shared infrastructure, production, and non-production.
- [ ] Network host, central logs, app dev, and app prod projects are created under the right folders.
- [ ] Billing account is linked to each project.
- [ ] Required APIs are enabled in the right projects.
- [ ] Organization policy guardrails are reviewed and enforced per inheritance.
- [ ] Shared VPC host project and service project associations are active.
- [ ] Subnet CIDRs do not overlap and network access is granted per least privilege.
- [ ] Organization audit-log sink has an active writer identity and destination.
- [ ] Terraform state is stored securely with versioning and dedicated IAM permissions.
- [ ] Plan was reviewed; apply was approved; subsequent plan shows no unexpected drift.

## References

- [Landing zone design in Google Cloud](https://docs.cloud.google.com/architecture/landing-zones) — foundational components, architectural choices, and landing zone implementation roadmap.
- [Decide a resource hierarchy for your Google Cloud landing zone](https://docs.cloud.google.com/architecture/landing-zones/decide-resource-hierarchy) — organizing organization, folders, projects, bootstrap, and shared infrastructure.
- [Google Cloud resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy) — parent/child relationships and inheritance of IAM and organization policies.
- [Terraform Google provider: google_folder](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_folder) — creating folders with Terraform.
- [Terraform Google provider: google_project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project) — creating projects, folder parents, and billing accounts.
- [Terraform Google provider: google_project_service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service) — enabling APIs for projects.
- [Terraform Google provider: google_org_policy_policy](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy) — managing organization policies with API v2.
- [Terraform Google provider: Shared VPC host project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_shared_vpc_host_project) — enabling Shared VPC host projects.
- [Terraform Google provider: Shared VPC service project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_shared_vpc_service_project) — attaching service projects to host projects.
- [Terraform Google provider: organization logging sink](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/logging_organization_sink) — routing logs from the organization and child projects.
- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs) — remote state, authentication, locking, and backend configuration.
- [Manage baseline organization policy constraints](https://docs.cloud.google.com/organization-policy/manage-baseline-constraints) — default guardrails and impact on service account keys.
- [Enterprise foundations blueprint](https://docs.cloud.google.com/architecture/blueprints/security-foundations) — reference architecture for enterprise foundations on Google Cloud.

# Declaring Projects, APIs, and IAM with Terraform

When an organization creates multiple Google Cloud environments, manually creating projects, enabling APIs, and granting permissions easily leads to inconsistent configurations. One project may be missing a required API, another may have excessive permissions, or the operations team may not remember who changed IAM. Infrastructure as Code (IaC) solves this problem by describing infrastructure in configuration files that can be managed in Git, previewed before applying, and deployed repeatably.

Terraform is a declarative IaC tool. With Google Cloud, the `hashicorp/google` provider maps HCL resources into operations against Google Cloud APIs. You can describe a project, enable services through the Service Usage API, create service accounts, and assign IAM roles. Terraform tracks managed resources in state to determine how actual configurations should change when source code is updated.

In the CLOUD_PROVIDERS_GCP module, the project is the boundary for administration, billing, and IAM; APIs define which services are allowed to be used; IAM defines which principal can do what on resources. Managing all three with Terraform standardizes the foundation for Compute Engine, GKE, Cloud Run, Cloud Storage, BigQuery, and Cloud Monitoring.

After this lesson, you can:

- Explain Terraform's provider, resource, variable, dependency graph, and state.
- Prepare bootstrap permissions to create a project in an organization or folder.
- Declare a Google Cloud project and link a billing account.
- Enable APIs using `google_project_service` and manage API lifecycles.
- Create service accounts and grant IAM permissions following the principle of least privilege.
- Distinguish between `member`, `binding`, and `policy` IAM resources.
- Manage remote state, inspect plans, apply changes, and import existing resources.

## 1. How Does Terraform Manage Google Cloud?

### Declarative Structure

Terraform uses the HCL (HashiCorp Configuration Language) syntax. A configuration typically contains:

- **Provider:** plugin that connects Terraform to a platform, such as hashicorp/google.
- **Resource:** resource to create or manage, such as google_project and google_project_service.
- **Data source:** reads information about an existing resource without creating it.
- **Variable and local:** input parameters and shared values within the configuration.
- **Output:** values to display or pass to another module.
- **State:** mapping between resource addresses in the configuration and actual resources on Google Cloud.

Terraform reads `.tf` files, builds a dependency graph, and compares the desired configuration with state and data read from the provider. From there, `terraform plan` displays the planned actions before `terraform apply` executes them.

~~~mermaid
flowchart TD
    A[HCL in Git] --> B[Terraform init]
    B --> C[Google Provider]
    C --> D[Terraform plan]
    E[Terraform state] --> D
    F[Current Google Cloud] --> D
    D --> G[Review plan]
    G --> H[Terraform apply]
    H --> I[Google Cloud APIs]
    H --> E
~~~

### Providers and Resources

The provider configures how Terraform authenticates and calls APIs. A resource describes the lifecycle of a resource type. For example:

| Terraform resource | Google Cloud resource |
|---|---|
| google_project | Google Cloud project |
| google_project_service | An enabled API/service in a project |
| google_service_account | Service account |
| google_project_iam_member | A principal added to a role at the project level |
| google_project_iam_binding | Authoritative list of members for a role at the project level |
| google_project_iam_policy | Full IAM policy of the project |

A Terraform address like `google_project.application` is an identifier in configuration and state. It is not the project ID on Google Cloud. The project ID is immutable and globally unique; the project display name can be changed.

### Dependency Graph

Terraform automatically recognizes dependencies when one resource references an attribute of another resource. For example, if `google_project_service` takes `project` from `google_project.application.project_id`, Terraform creates the project first and then enables the API.

When a dependency cannot be expressed through a reference, you can use `depends_on`. Avoid broad use of `depends_on` if a direct reference already expresses the relationship, because too many explicit dependencies make the graph harder to understand and can unnecessarily delay operations.

## 2. Preparing Permissions and a Bootstrap Project

Creating a new project is an organization-level operation. The principal running Terraform needs permissions at the right scope before the configuration can create resources.

### Commonly Required Permissions

| Task | Commonly Used Permission or Role | Scope |
|---|---|---|
| Create a project in an organization or folder | roles/resourcemanager.projectCreator | Organization or folder where the project is created |
| Link a project to a billing account | roles/billing.user and corresponding billing link permissions | Billing account and project |
| Enable APIs | roles/serviceusage.serviceUsageAdmin | Target project |
| Create service accounts | roles/iam.serviceAccountAdmin | Target project |
| Modify a project's IAM policy | roles/resourcemanager.projectIamAdmin | Target project |
| Impersonate Terraform runner service account | roles/iam.serviceAccountTokenCreator | The impersonated service account |

Actual roles also depend on organization policies, how projects are created, billing, and managed resources. Ask your administrator to grant the exact required permissions according to organizational procedures. Do not use Owner at the organization level just to make Terraform work.

### What Is a Bootstrap Project?

Terraform needs an identity that can call Google Cloud APIs before the target project is created. The project hosting the APIs and resources supporting the deployment process is commonly called a bootstrap or administration project. This project may contain:

- APIs required to manage the organization, projects, billing, and IAM.
- Dedicated service accounts for running Terraform.
- Workload Identity Federation configuration or impersonation mechanisms.
- State buckets and shared resources for the IaC workflow.

Do not make the state bucket depend on the very state stored inside that bucket. Create and manage the backend bucket through a separate bootstrap configuration or an organization-approved platform process.

### Secure Authentication

On a development machine, you can use Application Default Credentials (ADC) after logging in with a privileged account. In CI/CD, prefer Workload Identity Federation or service account impersonation. Avoid creating and storing long-lived JSON service account keys in repositories, unprotected environment variables, or pipeline logs.

## 3. Initializing the Terraform Configuration

Create a working directory for the project, for example:

~~~text
gcp-project/
├── versions.tf
├── provider.tf
├── variables.tf
├── main.tf
├── outputs.tf
└── terraform.tfvars
~~~

### Declaring Terraform and the Provider

In `versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}
~~~

Terraform selects a matching provider version upon initialization. Inspect and commit the `.terraform.lock.hcl` file so subsequent runs use the same verified provider version. When upgrading versions, perform it in a reviewed change and inspect the plan.

In `provider.tf`:

~~~hcl
provider "google" {
  project = var.bootstrap_project_id
  region  = var.region

  # Optional: run Terraform using a dedicated service account.
  impersonate_service_account = var.terraform_runner_service_account
}
~~~

`project` in the provider is the default project for resources that do not specify their own project. In the following examples, project and API resources will explicitly specify the target project. The service account used for impersonation must have appropriate permissions granted to the principal running Terraform.

### Declaring Input Variables

In `variables.tf`:

~~~hcl
variable "bootstrap_project_id" {
  description = "Project used to initialize and call Google Cloud APIs."
  type        = string
}

variable "terraform_runner_service_account" {
  description = "Email of the service account Terraform will impersonate."
  type        = string
}

variable "project_id" {
  description = "Globally unique project ID for the workload."
  type        = string
}

variable "project_name" {
  description = "Display name of the project."
  type        = string
}

variable "folder_id" {
  description = "Numeric ID of the folder containing the project."
  type        = string
}

variable "billing_account" {
  description = "Billing account ID linked to the project."
  type        = string
}

variable "region" {
  description = "Default region for regional resources."
  type        = string
  default     = "asia-southeast1"
}

variable "operations_group" {
  description = "Google Group email of the operations team."
  type        = string
}
~~~

In `terraform.tfvars`, provide environment-specific values. The example below uses sample data and must be replaced with real IDs from your organization:

~~~hcl
bootstrap_project_id             = "platform-bootstrap-prod"
terraform_runner_service_account = "terraform-runner@platform-bootstrap-prod.iam.gserviceaccount.com"
project_id                        = "customer-api-prod-123"
project_name                      = "Customer API Production"
folder_id                         = "123456789012"
billing_account                   = "000000-111111-222222"
region                            = "asia-southeast1"
operations_group                  = "gcp-operations@example.com"
~~~

Do not commit files containing secrets or sensitive data. Project ID, folder ID, and billing account ID values are not passwords, but they should still follow internal configuration management rules. Variables can be supplied via pipelines or separately managed `.tfvars` files.

## 4. Declaring a Google Cloud Project

The `google_project` resource creates a project and attaches it to an organization or folder. The following example places the project in a folder and links a billing account.

In `main.tf`:

~~~hcl
resource "google_project" "application" {
  project_id      = var.project_id
  name            = var.project_name
  folder_id       = var.folder_id
  billing_account = var.billing_account

  # Do not automatically create the default VPC network in the project.
  auto_create_network = false

  lifecycle {
    prevent_destroy = true
  }
}
~~~

`folder_id` is the ID of the folder containing the project. If creating a project directly under an organization, use `org_id` instead of `folder_id`; do not declare both simultaneously. Without permissions or an eligible billing account, creation or billing linkage will fail.

### Why Disable the Default Network?

When creating a project, automatically creating the default VPC network can generate default subnets and firewall rules across many regions. In production environments, teams typically want to design networks explicitly according to architecture and security policies. `auto_create_network = false` prevents creating the default network; VPCs and subnets can then be declared with dedicated resources in the networking lessons.

### Protecting the Project from Accidental Deletion

`lifecycle { prevent_destroy = true }` causes Terraform to reject plans containing a destroy action for the resource while this block remains in the configuration. This is a useful safeguard for production projects, but it does not replace review processes, IAM permissions, and organization policies. If the resource block is removed completely from the configuration, Terraform no longer sees that lifecycle rule; therefore, carefully review all changes involving projects and state.

The Project ID cannot be changed after creation. If you need to change the display name, you can update `name`; if you need a different project ID, that is a new project and requires a resource migration plan.

## 5. Enabling Google Cloud APIs with Terraform

A Google Cloud API must be enabled in a project before workloads can use the corresponding service. Terraform uses the `google_project_service` resource to manage this state via the Service Usage API.

Add to `main.tf`:

~~~hcl
locals {
  project_services = toset([
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "compute.googleapis.com",
    "run.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])
}

resource "google_project_service" "apis" {
  for_each = local.project_services

  project = google_project.application.project_id
  service = each.value

  # Do not automatically disable the API when removing the resource from configuration.
  disable_on_destroy = false
}
~~~

Terraform creates one `google_project_service.apis` instance for each API in the set. `project` references `google_project.application.project_id`, so Terraform knows it must create the project before enabling APIs.

`disable_on_destroy = false` keeps the API enabled if the resource is removed from configuration or state. This reduces the risk of accidentally disabling an API currently used by workloads. If an organization wants to manage API disabling as well, establish a separate process, inventory dependencies, and review the impact before changing this attribute.

### Choosing APIs by Workload

Avoid enabling every available API. Only declare the services your workload needs:

| API | When Needed |
|---|---|
| compute.googleapis.com | VMs, disks, VPCs, firewalls, and Compute Engine resources |
| container.googleapis.com | Google Kubernetes Engine |
| run.googleapis.com | Cloud Run |
| storage.googleapis.com | Cloud Storage |
| bigquery.googleapis.com | BigQuery |
| logging.googleapis.com | Cloud Logging and log ingestion |
| monitoring.googleapis.com | Cloud Monitoring and metrics |
| iam.googleapis.com | Managing service accounts and related IAM |
| cloudresourcemanager.googleapis.com | Managing projects and resource hierarchy |
| serviceusage.googleapis.com | Enabling, disabling, and checking API status |

Enabling an API can take some time to complete and propagate. The Terraform provider usually handles waiting for the operation, but pipelines still need sensible retry handling for operations depending on newly enabled services.

### APIs Required in the Bootstrap Project

The resource creating a project calls the Cloud Resource Manager API; the resource enabling APIs calls the Service Usage API. Therefore, the project used to run Terraform must already have the required APIs enabled and the principal must have corresponding permissions. Enabling an API in the target project does not automatically enable that API in the bootstrap project.

## 6. Creating Service Accounts and Granting IAM

### Creating a Service Account for the Workload

A service account represents a workload or automated component that needs to call Google Cloud APIs. Do not use personal user accounts as application runtime identities.

~~~hcl
resource "google_service_account" "runtime" {
  project      = google_project.application.project_id
  account_id   = "customer-api-runtime"
  display_name = "Customer API runtime"

  depends_on = [
    google_project_service.apis,
  ]
}
~~~

`depends_on` ensures the APIs in the list have been managed before creating the service account. Because the service account resource references the project ID, the project is also created first.

### Granting Permissions with google_project_iam_member

For example, the workload needs to write logs to Cloud Logging:

~~~hcl
resource "google_project_iam_member" "runtime_log_writer" {
  project = google_project.application.project_id
  role    = "roles/logging.logWriter"
  member  = format("serviceAccount:%s", google_service_account.runtime.email)
}
~~~

`google_project_iam_member` adds one principal to one role. It does not manage the entire member list of that role. This is usually the right choice when multiple independent teams or modules manage different permissions on one project.

If the operations team needs to view metrics and logs, read permissions can be granted as needed:

~~~hcl
resource "google_project_iam_member" "operations_monitoring_viewer" {
  project = google_project.application.project_id
  role    = "roles/monitoring.viewer"
  member  = format("group:%s", var.operations_group)
}

resource "google_project_iam_member" "operations_logging_viewer" {
  project = google_project.application.project_id
  role    = "roles/logging.viewer"
  member  = format("group:%s", var.operations_group)
}
~~~

Only grant roles genuinely required for the task. Do not grant `roles/owner`, `roles/editor`, or broad organization permissions just to avoid permission errors during deployment.

### Distinguishing member, binding, and policy

The three project-level IAM resources have different levels of authoritativeness:

| Resource | Management Scope | Impact |
|---|---|---|
| google_project_iam_member | A single role–member pair | Adds or removes a specific member; other members of the role are managed independently |
| google_project_iam_binding | Entire member list for one role | When applied, the role's member list is set to match the configuration |
| google_project_iam_policy | Entire IAM policy of the project | Replaces the full policy; can remove undeclared permissions |

Do not declare `google_project_iam_binding` and `google_project_iam_member` managing the same role on the same project because the two resources can overwrite each other's changes. `google_project_iam_policy` has the largest blast radius; only use it when a dedicated configuration truly owns the entire IAM policy.

### Least Privilege and Inherited Permissions

IAM on Google Cloud is inherited down the resource hierarchy: organization, folder, project, and child resources. When investigating a permission, inspect both directly assigned policies and inherited policies. A principal may hold permissions through a group or folder even if it does not appear directly in the IAM resources managed by Terraform.

Before changing IAM:

- Identify whether the principal is a user, group, service account, or workload identity.
- Choose the role with the fewest permissions that satisfies the task.
- Choose the appropriate project or resource scope.
- Check inherited permissions and existing bindings.
- Avoid removing members managed by the system or other teams.
- Verify the application works with the actual identity after granting permissions.

## 7. Combining Project, APIs, and IAM into One Configuration

The resources above can reside in the same root module. Terraform orders them automatically based on references and `depends_on`:

~~~mermaid
flowchart TD
    A[google_project.application] --> B[google_project_service.apis]
    B --> C[google_service_account.runtime]
    C --> D[google_project_iam_member.runtime_log_writer]
    A --> D
~~~

Logical order:

1. Create the project in the folder and link the billing account.
2. Enable APIs required for the workload.
3. Create the service account after the IAM API is ready.
4. Grant the role to the service account on the project.
5. Export the project ID and service account email for other modules to use.

In `outputs.tf`:

~~~hcl
output "project_id" {
  description = "Project ID of the workload."
  value       = google_project.application.project_id
}

output "runtime_service_account_email" {
  description = "Runtime identity of the application."
  value       = google_service_account.runtime.email
}
~~~

Outputs are not a place to store secrets. If an output contains sensitive values, mark it `sensitive = true`, but remember state may still store that value and must be protected.

## 8. Managing Terraform State Securely

### Why Is State Important?

Terraform state stores resource mappings, resource IDs, metadata, and sometimes sensitive attribute values. If state is lost, Terraform may no longer recognize created resources; if state is tampered with or exposed, others can cause infrastructure changes or read sensitive information.

Do not commit `terraform.tfstate`, state backups, or plan files that may contain sensitive data to Git. Do not treat `sensitive = true` as state encryption; this attribute mainly restricts display in certain CLI outputs.

### Using the Google Cloud Storage Backend

Example backend configuration:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state"
    prefix = "gcp/production/customer-api"
  }
}
~~~

The bucket must be created before `terraform init` initializes the backend. Use IAM to restrict who can read/write state, enable object versioning so previous versions can be recovered, and monitor audit logs. The GCS backend supports state locking to prevent multiple runs from writing state concurrently.

The state bucket should reside in a separately governed platform project. Separate state read permissions from workload deployment permissions if your workflow allows. Anyone with permission to read state can view sensitive values written into state by providers.

### Terraform Lifecycle Commands

~~~bash
# Download providers and initialize backend
terraform init

# Standardize HCL formatting
terraform fmt -recursive

# Check syntax and configuration structure
terraform validate

# Create a plan to review before making changes
terraform plan -out=tfplan

# Inspect the saved plan
terraform show tfplan

# Apply only the reviewed plan
terraform apply tfplan

# Check for drift after deployment
terraform plan
~~~

In production pipelines, separate the plan and apply steps to allow human review. Plan files should be stored in an access-controlled location with a short retention period because they may contain sensitive data. When the configuration changes after generating a plan, generate a new plan rather than applying the old one.

## 9. Importing and Managing Existing Resources

Many organizations already have projects, APIs, or IAM created manually. Do not create a duplicate Terraform resource alongside an existing resource. Import the resource into state, then adjust HCL to reflect the desired state.

Example importing an existing project:

~~~bash
terraform import google_project.application existing-project-id
~~~

After importing:

1. Write HCL configuration matching the actual project.
2. Run `terraform plan` to see differences between HCL, state, and the remote object.
3. Adjust the configuration or import process until the plan no longer proposes unintended changes.
4. Only apply once you understand the impact of every change.

Importing only brings the resource into state; it does not automatically generate complete HCL configuration. For IAM, inventory existing policies and select the appropriate `member`/`binding`/`policy` resource. Transitioning from manual management to Terraform should be done in small permission groups to reduce the risk of accidentally deleting permissions currently in use.

## 10. Drift, Changes, and Troubleshooting

### Configuration Drift

Drift occurs when the actual state differs from the Terraform configuration—for example, an administrator manually enables an extra API or grants a role outside Terraform. `terraform plan` can detect some differences when the provider refreshes remote state.

When drift is detected, determine whether the change was intentional:

- If the change is valid, update HCL so the configuration reflects the new decision.
- If the change bypassed the process, consider letting Terraform return the resource to the desired state after assessing the impact.
- If the resource is not yet managed by Terraform, consider importing it before editing.

Do not run `apply` just to make the plan clean without understanding why drift appeared.

### Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| Cannot create project | Missing projectCreator role, wrong folder ID, or blocked by organization policy | Check principal, folder/organization, and project creation policies |
| Cannot link billing | Missing permissions on billing account or inactive billing account | Check billing account and project billing link permissions |
| Enabling API denied | Missing Service Usage Admin or required API not enabled in bootstrap project | Check serviceusage.services.enable permission and bootstrap project APIs |
| Service account creation fails | IAM API not enabled or principal lacks permissions | Check iam.googleapis.com and Service Account Admin role |
| IAM member conflicts | Multiple Terraform resources managing the same role or binding | Standardize ownership and use a single IAM model per role |
| Apply reports project is in use | Dependent resources or project has protection rules | Check dependencies and do not delete the project without a migration plan |
| Terraform repeatedly proposes changes | Drift, provider/API defaults, or inconsistent configuration | Inspect diff, normalize attributes, and import resources if needed |
| State lock is held | A previous run stopped abnormally | Confirm no Terraform process is still running before unlocking per procedure |

### Handling State Locks

Do not immediately run `terraform force-unlock` when seeing a lock error. First check whether a pipeline, terminal, or another operator running Terraform is still active. Only unlock after confirming the lock belongs to a stopped run and you have authorization to manage state. Unlocking improperly can allow two processes to modify state concurrently and corrupt managed data.

## 11. Safe Team Collaboration Workflow

A reviewed IaC workflow typically consists of:

1. An engineer creates a branch and edits HCL.
2. CI runs `terraform fmt -check` and `terraform validate`.
3. The pipeline creates a plan using an identity with controlled permissions.
4. Reviewers inspect project, API, and IAM diffs, billing impact, and potentially destructive changes.
5. An authorized approver approves the plan.
6. The pipeline applies the exact approved plan.
7. The system records logs, state versions, and deployment results.
8. The team monitors drift and periodically reviews permissions.

Split root modules or states by environment and ownership boundaries. For example, the bootstrap project, network foundation project, and workload projects can have separate states. This separation reduces the blast radius when an apply fails and clarifies operational team permissions.

### Practices to Maintain

- Commit `.terraform.lock.hcl` to pin tested providers.
- Use shared modules for naming, labels, APIs, and IAM when there are many similar projects.
- Use variables for project ID, folder, billing, and region; do not hardcode environment differences inside resources.
- Use separate service accounts or workload identities per pipeline.
- Protect the state backend, plan artifacts, and impersonation permissions.
- Do not grant broad permissions just to make a single apply succeed.
- Review any change that can delete a project, disable an API, or replace an IAM policy.
- Save required outputs and never emit secrets into logs.

## 12. Pre-Production Deployment Checklist

- [ ] Principal running Terraform has properly scoped bootstrap permissions.
- [ ] Required APIs for the bootstrap project are enabled.
- [ ] Project ID, folder ID, and billing account are confirmed.
- [ ] Project is created with an appropriate network configuration.
- [ ] Only APIs needed by the workload are enabled.
- [ ] `disable_on_destroy` is set according to API lifecycle policy.
- [ ] Separate service accounts are created for workloads and pipelines.
- [ ] IAM uses least-privilege roles and exact principals.
- [ ] No conflicts between `google_project_iam_member`, binding, and policy.
- [ ] State uses a remote backend, locking, and versioning.
- [ ] `.terraform.lock.hcl` is committed; state and plan files are excluded from Git.
- [ ] Plan is reviewed before apply.
- [ ] Import and drift-handling procedures exist.
- [ ] Safeguards exist to prevent accidental deletion of production projects.

## 13. Conclusion

Terraform turns projects, APIs, and IAM into configurations that can be reviewed, reproduced, and managed across their lifecycle. `google_project` establishes the administrative boundary; `google_project_service` enables required services; `google_service_account` and IAM resources define which workload or user group is permitted to perform which actions.

To operate safely, prepare a least-privilege bootstrap identity, manage state remotely, choose the right IAM model, and always review plans before applying. When Terraform configuration becomes the source of truth for projects, APIs, and IAM, organizations can scale GCP environments consistently and control changes more effectively.

## References

- [Terraform Google Cloud provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Google Cloud projects with Terraform](https://cloud.google.com/docs/terraform/resource-management/managing-projects)
- [google_project resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project)
- [google_project_service resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service)
- [google_project_iam resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_iam)
- [Google Cloud Storage backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Google Cloud authentication for Terraform](https://cloud.google.com/docs/terraform/authentication)

# Environment Separation, Parameterization, and Dependency Management

A Terraform configuration often starts with a single test environment. As an application grows, the same infrastructure needs to be deployed across dev, staging, and production. Copying entire configuration files for each environment easily leads to drift between copies; sharing a single state and a single permission set means one mistake can impact production.

A sound design addresses three things together: **separating environment boundaries**, **reusing configurations via modules and variables**, and **declaring proper dependency relationships** so Terraform plans in a safe order. On Google Cloud, the common model is one root module directory per environment, shared modules in a separate directory, and each environment having its own backend/state and appropriate access permissions.

In the **CLOUD_PROVIDERS_GCP** module, this organization enables consistent deployment from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases. Operations teams can test changes in dev, verify in staging, and promote the same module version to production with separate parameters and permissions.

After this lesson, you can:

- Choose environment boundaries aligned with Google Cloud projects and IAM permissions.
- Organize root modules by environment and reusable modules.
- Parameterize project, region, resource names, and environment-specific settings.
- Manage variables, defaults, validation, and sensitive data.
- Design independent backends/states for each environment.
- Distinguish implicit dependencies, explicit dependencies, and cross-root-module dependencies.
- Build a controlled plan, review, apply, and module upgrade workflow.

## 1. Why Separate Environments?

Environments serve different purposes and carry different risk levels:

| Environment | Purpose | Typical Configuration Characteristics |
|---|---|---|
| Dev | Rapid development, feature testing | Smaller resources, test data, frequent create/destroy |
| Staging / QA | Integration testing and pre-release validation | Structurally close to production, sanitized data |
| Production | Serving real users | High availability, change controls, backups, logging, and strict IAM |

Separating environments is not just changing a resource name suffix. Boundaries should be reflected in:

- **Google Cloud project**: each environment has its own project, or at least clear project boundaries by application and area of responsibility.
- **IAM and deployment identity**: separate service account or workload identity per environment; the dev pipeline has no permission to apply to production.
- **Terraform state**: each environment has its own state so `plan` and `apply` only affect the assigned resource set.
- **Backend and access permissions**: production state has stricter read/write permissions than dev state.
- **Configuration and data**: project ID, region, sizing, domain, retention, replica counts, and backup policies are set per environment.

For example, an organization can use project IDs `app-dev`, `app-staging`, and `app-prod`. This naming immediately identifies the deployment target in CLI commands, logs, and IAM policies. In larger systems, a Shared VPC or shared network project can be managed separately; permissions to connect to shared resources must be clearly designed.

## 2. Choosing a Multi-Environment Terraform Structure

### 2.1. The Modules and Environments Pattern

Google Cloud recommends separating shared configuration into a `modules/` directory and creating dedicated root configurations for each environment under `environments/`.

Example structure for a network service:

~~~text
network-service/
├── modules/
│   └── vpc/
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
└── environments/
    ├── dev/
    │   ├── backend.tf
    │   ├── main.tf
    │   ├── variables.tf
    │   └── dev.tfvars
    ├── staging/
    │   ├── backend.tf
    │   ├── main.tf
    │   ├── variables.tf
    │   └── staging.tfvars
    └── prod/
        ├── backend.tf
        ├── main.tf
        ├── variables.tf
        └── prod.tfvars
~~~

Each `environments/<env>` directory is a **root module**: the directory where `terraform init`, `plan`, and `apply` are executed. The root module calls shared modules using relative paths. `.tfvars` files supply environment-specific values.

The `vpc` module only describes how to create a VPC and accepts parameters such as project ID, network name, and subnet mode. The root module decides which project, region, and values to pass to that module. As a result, VPC creation logic is written once and deployed across multiple projects.

Avoid cramming every application and infrastructure layer into one huge root module. Google Cloud recommends keeping each state under 100 resources, ideally a few dozen resources. Splitting by application or component boundary speeds up plans, reduces blast radius, and delegates ownership to individual teams.

### 2.2. Why Not Use CLI Workspaces as a Security Boundary?

Terraform CLI workspaces represent multiple isolated states within the same working directory and backend. When switching workspaces, Terraform uses a different state, but the configuration, backend, and authentication mechanism remain tied to the same working directory.

Workspaces are useful when multiple similar deployments share the same configuration and the same access permissions. However, workspaces are unsuitable when environments require separate credentials or access controls. Anyone with access to the shared backend can switch workspaces and operate on another state.

With Google Cloud, prefer dedicated root module directories for `dev`, `staging`, and `prod`, each using an independent backend/state and specifying a deployment identity with permissions on the corresponding project. Each directory normally uses the `default` workspace.

| Criterion | Dedicated Environment Directories | CLI Workspaces |
|---|---|---|
| Root configuration | Each environment has its own directory | Shared working directory |
| Backend | Can be configured separately | Shared backend in the working directory |
| State access control | Can be separated by bucket or backend | Hard to isolate permissions per workspace within the same backend |
| Environment config | Dedicated files and variables | Typically relies on variables and `terraform.workspace` |
| Best suited for | Environments needing clear IAM, project, and blast radius boundaries | Multiple similar deployments sharing permissions and lifecycle |

Do not rely on `terraform.workspace == "prod"` as the sole protection layer for production. Google Cloud IAM permissions and state write permissions form the real boundary.

## 3. Creating Shared Modules

A module should have a clear responsibility, a compact input interface, and meaningful outputs. Example VPC module:

**modules/vpc/main.tf**

~~~hcl
resource "google_compute_network" "this" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = var.auto_create_subnetworks
  routing_mode            = "REGIONAL"
}
~~~

**modules/vpc/variables.tf**

~~~hcl
variable "project_id" {
  description = "Google Cloud project containing the VPC."
  type        = string
  nullable    = false
}

variable "network_name" {
  description = "VPC name within the project."
  type        = string
  nullable    = false
}

variable "auto_create_subnetworks" {
  description = "Whether to automatically create regional subnets."
  type        = bool
  default     = false
}
~~~

**modules/vpc/outputs.tf**

~~~hcl
output "network_self_link" {
  description = "Self-link of the created VPC."
  value       = google_compute_network.this.self_link
}

output "network_name" {
  description = "VPC name."
  value       = google_compute_network.this.name
}
~~~

A module should not try to guess the environment from directory names, branch names, or global variables. Accept required values via input variables. Common, stable values can have defaults in the module; values that vary by project or environment should be required parameters.

If a module needs multiple resources of the same type, use `for_each` with stable keys so Terraform tracks each instance individually. Keys should carry domain meaning such as `web`, `private`, or `database`; avoid generating random keys. For lists whose order may change, `for_each` generally preserves resource identity much better than index-based `count`.

## 4. Declaring Providers and Root Modules per Environment

Each root module declares the required Terraform and provider versions. The example below uses the Google provider `8.12` branch; in real projects, pick a version compatible with the resources in use, pin versions in `.terraform.lock.hcl`, and upgrade in a controlled manner.

**environments/dev/main.tf**

~~~hcl
terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.12"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

module "vpc" {
  source = "../../modules/vpc"

  project_id              = var.project_id
  network_name            = var.network_name
  auto_create_subnetworks = false

  # The API must be enabled before the module creates the VPC.
  # The module does not directly reference attributes of this API resource.
  depends_on = [google_project_service.compute]
}
~~~

**environments/dev/variables.tf**

~~~hcl
variable "project_id" {
  description = "Project ID for the dev environment."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be 6-30 characters, start with a lowercase letter, and contain only lowercase letters, numbers, or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  nullable    = false

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "region" {
  description = "Region where resources are deployed."
  type        = string
  default     = "asia-southeast1"
}

variable "network_name" {
  description = "Environment VPC name."
  type        = string
  nullable    = false
}
~~~

**environments/dev/dev.tfvars**

~~~hcl
project_id   = "company-app-dev"
environment  = "dev"
region       = "asia-southeast1"
network_name = "app-dev-vpc"
~~~

In staging and production, the root module calls the same `../../modules/vpc` module but uses its own `project_id`, `network_name`, backend, and deployment identity. The directories can share the same `variables.tf` content; each environment has its own `.tfvars` file. If major architectural differences are required, create specialized modules or root modules rather than scattering environment conditionals throughout a single configuration.

Note: the Compute Engine API enablement example illustrates a module-level dependency. In real environments, required APIs may include `compute.googleapis.com`, `container.googleapis.com`, `run.googleapis.com`, or other APIs depending on services. Organize API lists in a foundation module aligned with project permissions and lifecycle.

## 5. Parameterizing with Variables, Locals, and tfvars

### 5.1. Input Variables

Input variables are the interface through which a root or parent module passes values to a child module. A variable should declare:

- `type`: data type such as `string`, `number`, `bool`, `list(string)`, `set(string)`, `map(string)`, or `object({...})`.
- `description`: purpose and value format.
- `default`: default value if truly safe and appropriate for all callers.
- `validation`: validity rules to block misconfiguration before `apply`.
- `sensitive`: masks the value in CLI output and certain logs.
- `nullable`: controls whether `null` values are allowed.

Example validating region and environment:

~~~hcl
variable "region" {
  description = "Region for workload deployment."
  type        = string
  default     = "asia-southeast1"

  validation {
    condition = contains(
      ["asia-southeast1", "asia-east1", "us-central1"],
      var.region
    )
    error_message = "Region is not in the approved list."
  }
}
~~~

Validation should enforce rules within the module's scope, such as organization-approved regions, bounded replica counts, or valid resource name formatting. Avoid duplicating excessive validation for rules already checked by the provider or Google Cloud.

The project ID regex above checks basic format. Google Cloud also enforces additional naming rules and reserved words; passing Terraform validation does not replace checks during project creation.

### 5.2. Locals for Derived Values

`locals` name expressions computed from inputs. They are not input variables and cannot be overridden from the CLI:

~~~hcl
locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    service     = "checkout"
  }
}
~~~

Use `locals` to standardize labels, resource names, or repeatedly computed values. Keep environment differences in input variables and `.tfvars` files; avoid duplicating the same constant across multiple resources.

### 5.3. tfvars Files and Precedence

`.tfvars` files store environment-specific configuration values. The Terraform CLI automatically loads `terraform.tfvars`, `terraform.tfvars.json`, and any `*.auto.tfvars` or `*.auto.tfvars.json` files. A specific file can be passed with `-var-file`.

When the same variable receives multiple values, typical precedence from highest to lowest is:

1. `-var` and `-var-file` options on the command line, in the order specified.
2. `*.auto.tfvars` and `*.auto.tfvars.json` files, in lexical filename order.
3. `terraform.tfvars.json`.
4. `terraform.tfvars`.
5. Environment variables prefixed with `TF_VAR_`.
6. `default` values in variable declarations.

Example running plan for dev:

~~~bash
terraform plan -var-file="dev.tfvars"
~~~

Pipelines can pass variable files explicitly to avoid accidentally using another environment's configuration. In CI/CD, variables can be injected via `TF_VAR_project_id`, `TF_VAR_region`, or the pipeline's variable management system. Do not pass secrets on the command line if commands can be recorded in shell history or logs.

## 6. Managing Sensitive Data and Authentication

Marking `sensitive = true` makes Terraform mask values in display output, but **does not automatically strip the value from state or plan files**. If a resource accepts a password or secret via a persisted argument, that value may still reside in state.

Example declaring a sensitive variable:

~~~hcl
variable "database_password" {
  description = "Database password provided from secret manager."
  type        = string
  sensitive   = true
}
~~~

Operational rules:

- Never commit files containing passwords, API tokens, or private keys to Git.
- Never store service account JSON keys in `terraform.tfvars`.
- Prefer Application Default Credentials locally; developers can authenticate with `gcloud auth application-default login`.
- In CI/CD, use Workload Identity Federation or service account impersonation instead of long-lived keys.
- Use Secret Manager to manage application secrets. Only pass secrets into Terraform when truly necessary and when state storage implications are understood.
- Protect state read access like sensitive data read access; restrict which people and pipelines can access the state bucket.

Terraform 1.10 and later supports `ephemeral = true` for certain inputs/outputs and valid contexts. Ephemeral values are not written to state or plan files, making them suitable for short-lived tokens. However, they have restrictions on where they can be referenced and cannot be used arbitrarily in every provider argument. Check resource/provider documentation before applying. `sensitive` and `ephemeral` solve two different problems: masking display output versus excluding values from state/plan.

## 7. Separating Backends and State on Google Cloud

Terraform state stores the mapping between resources in configuration and real objects on Google Cloud. If dev and prod share state, a plan in one environment can alter or delete resources in the other. Therefore, each environment root module needs an independent state.

### 7.1. Using the Cloud Storage Backend

The GCS backend stores state as an object in a Cloud Storage bucket. The bucket must exist before Terraform initializes the backend. The GCS backend supports state locking to prevent concurrent state writes; Google/HashiCorp recommend enabling Object Versioning to recover state after accidental deletion or operational mistakes.

**environments/dev/backend.tf**

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state-dev"
    prefix = "network-service"
  }
}
~~~

**environments/prod/backend.tf**

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state-prod"
    prefix = "network-service"
  }
}
~~~

Staging has its own backend following the same pattern. Use a dedicated bucket for production when independent IAM, retention, encryption, or access governance is required. If sharing a bucket, each environment still needs a distinct prefix; however, bucket-level IAM may not provide fine-grained enough isolation.

Backend config is processed during `terraform init`; you cannot reference input variables such as `var.environment` inside the `backend` block. Therefore, declare a dedicated backend per root module or pass static backend config via `-backend-config`.

Create the state bucket via an independent bootstrap process. Never have a configuration create its own state bucket as a managed resource, because the backend must exist before `terraform init` can store state.

### 7.2. Protecting State

- Enable Object Versioning on the bucket so previous state versions can be recovered.
- Enable uniform bucket-level access and grant only necessary IAM to pipelines/operations teams.
- Never make the bucket public and never commit `terraform.tfstate`, state backups, or plan artifacts to Git.
- Use state locking; do not use `-lock=false` to bypass a lock held by another process.
- Never edit state JSON directly. When bindings must change, use appropriate `terraform state` commands and review first.
- Treat state as sensitive data because it may contain attribute values and secrets.

Initialize the backend:

~~~bash
cd environments/dev
terraform init
~~~

If changing the backend of a configuration that already manages resources, plan a state migration using `terraform init -migrate-state`. Do not change the bucket or prefix casually and run `apply`, because Terraform could initialize an empty state and propose recreating existing resources.

## 8. Managing Dependencies in Terraform

Terraform builds a dependency graph from references in the configuration. Independent resources can be processed in parallel; dependent resources are executed in the appropriate order.

### 8.1. Implicit Dependencies via References

When one resource uses an attribute of another resource, Terraform infers the dependency automatically:

~~~hcl
resource "google_compute_network" "app" {
  project                 = var.project_id
  name                    = "app-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  project       = var.project_id
  name          = "app-private"
  region        = var.region
  network       = google_compute_network.app.id
  ip_cidr_range = "10.20.0.0/20"
}
~~~

`google_compute_subnetwork.private` references `google_compute_network.app.id`, so Terraform knows the VPC must exist before the subnet. This is the preferred approach because the dependency is expressed directly through the data the resource needs.

### 8.2. Explicit Dependencies with depends_on

Sometimes an operational relationship exists without any attribute being referenced. For example, the VPC module requires the Compute Engine API to be enabled first, but the module only accepts `project_id` and `network_name` and does not read outputs from `google_project_service`.

In that case, you can declare:

~~~hcl
resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

module "vpc" {
  source       = "../../modules/vpc"
  project_id   = var.project_id
  network_name = var.network_name

  depends_on = [google_project_service.compute]
}
~~~

`depends_on` is supported in `resource` and `module` blocks, accepting a list of resource or module references within the same calling module. Use it when there is a hidden dependency Terraform cannot infer. Avoid adding `depends_on` to every resource just to force sequential execution: this widens the dependency graph, makes plans harder to read, and can force Terraform to wait on unknown values.

### 8.3. Dependencies Between Modules

When a child module consumes an output from another module, Terraform infers the ordering automatically:

~~~hcl
module "vpc" {
  source       = "../../modules/vpc"
  project_id   = var.project_id
  network_name = var.network_name
}

module "private_service" {
  source     = "../../modules/private-service"
  project_id = var.project_id
  network_id = module.vpc.network_self_link
}
~~~

`module.private_service` receives an output from `module.vpc`, so the VPC module is processed before the component that depends on that output. Designing modules with clear inputs and outputs keeps the dependency graph natural and easy to inspect.

## 9. Dependencies Between Root Modules and Sharing Outputs

Two root modules are two independent configurations. Terraform does not build a shared dependency graph across them. For example, network has its own state and application has its own state. If the application needs the network ID, remote state can be used to read published outputs:

~~~hcl
data "terraform_remote_state" "network" {
  backend = "gcs"

  config = {
    bucket = "company-terraform-state-dev"
    prefix = "network-service"
  }
}

module "application" {
  source = "../../modules/application"

  project_id = var.project_id
  network_id = data.terraform_remote_state.network.outputs.network_self_link
}
~~~

Google Cloud recommends Cloud Storage or Terraform Enterprise as the backend when sharing information between root modules. Use remote state for outputs with clear contracts, such as network self-links, subnet IDs, or service account emails.

The consumer must read state from the matching environment. The production root module must reference the production backend/state; never use outputs from dev state to configure production resources.

Two things require attention:

1. Remote state only provides data; it does not orchestrate apply ordering between two root modules. The pipeline must deploy network first, then run application.
2. Readers of remote state need permission to read the state snapshot. Because state can contain more data than the referenced outputs, never put secrets in outputs and grant state access according to least privilege.

If you need to query a resource created manually or managed by another system, use a Google provider data source. Avoid using data sources to look up resources managed by another Terraform root module, because relying on resource names and structure can break when the upstream configuration changes. For Terraform-managed resources in another configuration, prefer an output contract via remote state or a governed configuration-sharing mechanism.

## 10. Managing Provider and Module Versions

Terraform needs provider plugins to communicate with Google Cloud. Declare providers in `required_providers`:

~~~hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.12"
    }
  }
}
~~~

Version constraints define the range of installable versions. After `terraform init`, Terraform records the selected provider version and checksums in `.terraform.lock.hcl`. Commit this lock file to Git so developer machines and pipelines install the same provider version. Only update the lock file intentionally—for example, after reviewing changes and running tests with `terraform init -upgrade`.

For modules from the Terraform Registry, declare `version` to pin the module to a compatible release. For modules sourced from Git, use a stable tag or commit ref. For local modules, Terraform reads the source directly at that path; the `version` argument does not apply to local modules. The lock file currently tracks provider dependencies and does not lock remote module versions; therefore, pin remote module versions in the `module` block.

Example Registry module:

~~~hcl
module "network" {
  source  = "terraform-google-modules/network/google"
  version = "18.3.1"

  project_id   = var.project_id
  network_name = "app-network"
  routing_mode = "REGIONAL"

  subnets = [
    {
      subnet_name           = "app-private"
      subnet_ip             = "10.20.0.0/20"
      subnet_region         = var.region
      subnet_private_access = "true"
    }
  ]
}
~~~

Choose module versions compatible with the provider and Terraform versions your organization uses. When upgrading, read the changelog, run `plan` in dev, test in staging, and only then update the production version.

## 11. Deployment Workflow Across Dev, Staging, and Production

A controlled pipeline can deploy in the following sequence:

~~~mermaid
flowchart TD
    A["Module / variable changes in Git"] --> B["Format and validate"]
    B --> C["Plan with dev backend + tfvars"]
    C --> D["Review diff and apply dev"]
    D --> E["Integration testing in staging"]
    E --> F["Plan with staging state and permissions"]
    F --> G["Review and apply staging"]
    G --> H["Plan production"]
    H --> I["Infrastructure owner approval"]
    I --> J["Apply saved plan with prod identity"]
    J --> K["Monitor and record deployment results"]
~~~

Reference commands when running inside each environment directory:

~~~bash
terraform fmt -check
terraform init
terraform validate
terraform plan -var-file="dev.tfvars" -out="dev.tfplan"
terraform apply "dev.tfplan"
~~~

In staging and production, substitute the corresponding variable file and use that environment's backend. `terraform plan` must be reviewed to identify resources being created, updated, or destroyed. Saved plans must be protected because they may contain sensitive data. Do not use `-auto-approve` for production if the process requires infrastructure owner approval.

The pipeline should:

- Run from the right root module and select the right project.
- Authenticate using an environment-specific service account or Workload Identity Federation.
- Never use production credentials in dev jobs.
- Retain plan/apply logs, commit IDs, module versions, and approver records.
- Halt if validation, policy checks, or plan review fail.
- Execute root modules in the dependency order defined in the pipeline.

## 12. Common Mistakes When Separating Environments

| Mistake | Consequence | Resolution |
|---|---|---|
| Dev and prod share state | A plan in one environment can affect resources in the other | Separate root modules and backends/states |
| Only renaming resources using `terraform.workspace` | Backend permissions and credentials are still shared | Use separate directories, projects, IAM identities, and states |
| Copying entire configurations into multiple versions | Environments drift in logic over time | Extract shared logic into modules and pass parameters |
| Module has too many environment-specific variables | Confusing interface, many conditional branches | Keep inputs small, typed, and validated |
| Putting secrets in `tfvars` and committing to Git | Credential exposure | Secret Manager, ADC, WIF, and CI/CD secret stores |
| Assuming `sensitive` prevents state storage | Secrets can still reside in state | Protect state; use `ephemeral` where context allows |
| Overusing `depends_on` | Overly tight graph, hard-to-read and slow plans | Prefer output/attribute references; only declare hidden dependencies |
| Using data sources to find resources managed by another root module | Fragile dependency on names/attributes | Use an output contract via remote state |
| Not pinning providers/modules | Local machines and pipelines may use different versions | Version constraints, lock files, and module versions |
| Copying an environment directory with old state and applying | Terraform may propose recreating resources | Plan state migration and review plan before apply |

## 13. Pre-Production Checklist

- [ ] Production has its own Google Cloud project or an approved project boundary.
- [ ] Production service account/workload identity is separated from dev and staging.
- [ ] Production root module has its own backend and state.
- [ ] State bucket has Object Versioning, state locking, and least-privilege IAM enabled.
- [ ] Shared modules have clear inputs/outputs and do not rely on implicit environment names.
- [ ] `variables.tf` defines `type`, `description`, and `validation` for critical values.
- [ ] Only `.tfvars` files without secrets are committed to Git.
- [ ] Provider constraints and `.terraform.lock.hcl` have been reviewed.
- [ ] Implicit dependencies are expressed via references; `depends_on` is used only for hidden dependencies.
- [ ] Cross-root-module dependencies have output contracts and pipeline ordering.
- [ ] Production plan is reviewed, saved plans are protected, and approval is recorded.
- [ ] State recovery and migration plans exist before changing backends or splitting state.

## 14. Self-Check

1. Why does each environment need its own root module and state when dev and production have different IAM?
2. Which values should a reusable module accept via input variables?
3. Does `sensitive = true` guarantee a secret will not appear in state?
4. When does Terraform infer dependencies automatically, and when is `depends_on` needed?
5. Why are CLI workspaces unsuitable for separating environments that require distinct credentials?
6. How can an application root module read a network ID managed by a network root module?
7. Does `.terraform.lock.hcl` manage providers and remote modules in the same way?

**Suggested Answers**

1. Independent state limits `plan`/`apply` scope; separate root modules and backends isolate permissions, credentials, and blast radius.
2. Caller-varying values such as project ID, region, resource names, sizing, CIDRs, and environment policies. The module keeps defaults for genuinely common attributes.
3. No. `sensitive` masks values in display output; state can still store them. Protect the backend and use `ephemeral` where supported.
4. Terraform infers dependencies when a resource/module references another component's attribute or output. Use `depends_on` for hidden relationships that cannot be expressed via data references.
5. CLI workspaces share the same working directory and backend, making it difficult to isolate credentials and access control per environment.
6. Publish an output from the network root module, read it via `terraform_remote_state`, and orchestrate the pipeline so network applies before application.
7. No. The lock file tracks provider dependencies; remote modules must pin `version` or source `ref` in the `module` block.

## References

- [Google Cloud: Best practices for root modules](https://docs.cloud.google.com/docs/terraform/best-practices/root-modules)
- [Google Cloud: Best practices for cross-configuration communication](https://docs.cloud.google.com/docs/terraform/best-practices/cross-config-communication)
- [Google Cloud: Best practices for Terraform operations](https://docs.cloud.google.com/docs/terraform/best-practices/operations)
- [HashiCorp: Terraform CLI workspaces](https://developer.hashicorp.com/terraform/cli/workspaces)
- [HashiCorp: GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [HashiCorp: Input variables](https://developer.hashicorp.com/terraform/language/values/variables)
- [HashiCorp: Dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock)
- [HashiCorp: depends_on meta-argument](https://developer.hashicorp.com/terraform/language/meta-arguments/depends_on)
- [Terraform Registry: Google provider](https://registry.terraform.io/providers/hashicorp/google)
- [Terraform Registry: Google Cloud Network module](https://registry.terraform.io/modules/terraform-google-modules/network/google/latest)
